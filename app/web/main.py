"""FastAPI API and separate teacher/learner pages."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from langgraph.types import Command
from pydantic import BaseModel, Field

from app.core.config import UPLOAD_DIR
from app.core.llm import health_check
from app.learner.graph import build_learner_graph
from app.services.category_profiles import category_manifest
from app.services.generation_standards import reading_question_types
from app.services.task_repository import list_tasks, list_teachers, load_public_task
from app.teacher.graph import build_teacher_graph
from app.teacher.state import initial_teacher_state

ROOT = Path(__file__).resolve().parent.parent.parent
STATIC = Path(__file__).resolve().parent / "static"
MEETING_BRIEFING = (
    ROOT
    / "artifacts"
    / "presentations"
    / "expert_review"
    / "0730_meeting_briefing.html"
)
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

app = FastAPI(title="한국어 읽기·쓰기 평가 시스템")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


@app.get("/briefing", include_in_schema=False)
def meeting_briefing() -> FileResponse:
    """Serve the self-contained expert-meeting briefing."""
    if not MEETING_BRIEFING.exists():
        raise HTTPException(status_code=404, detail="미팅 브리핑 파일이 없습니다.")
    return FileResponse(MEETING_BRIEFING, media_type="text/html")


def _set_job(job_id: str, **values) -> None:
    with _jobs_lock:
        _jobs.setdefault(job_id, {}).update(values)


def _pending(result: dict | None) -> dict | None:
    interrupts = (result or {}).get("__interrupt__")
    return interrupts[0].value if interrupts else None


def _teacher_config(job: dict) -> dict:
    return {"configurable": {"thread_id": job["thread_id"]}}


def _run_teacher(job_id: str, value) -> None:
    job = _jobs[job_id]
    _set_job(job_id, status="running", error=None)
    try:
        result = job["graph"].invoke(value, _teacher_config(job))
        pending = _pending(result)
        if pending:
            _set_job(job_id, status="waiting_review", stage=pending["stage"], payload=pending)
        else:
            final = job["graph"].get_state(_teacher_config(job)).values
            _set_job(job_id, status="completed", stage="published", payload={
                "task_id": final.get("published_task_id"),
                "location": final.get("published_path"),
            })
    except Exception as exc:
        _set_job(job_id, status="failed", error=f"{type(exc).__name__}: {exc}")


def _run_learner(job_id: str, state: dict) -> None:
    _set_job(job_id, status="running", error=None)
    try:
        result = build_learner_graph().invoke(state)
        _set_job(job_id, status="completed", payload={
            "result": result["final_result"], "submission_id": result.get("submission_id")
        })
    except Exception as exc:
        _set_job(job_id, status="failed", error=f"{type(exc).__name__}: {exc}")


class PassageReview(BaseModel):
    decision: str
    note: str = ""
    reading_question_types: list[str] = Field(default_factory=list)
    writing_sentence_type: str = "writing"
    regeneration_targets: list[str] = Field(default_factory=list)
    approval_review: dict = Field(default_factory=dict)


class AssessmentReview(BaseModel):
    decision: str
    note: str = ""
    regeneration_targets: list[str] = Field(default_factory=list)
    approval_review: dict = Field(default_factory=dict)
    reading_regeneration_indexes: list[int] = Field(default_factory=list)
    writing_regeneration: bool = False


class LearnerSubmission(BaseModel):
    task_id: str
    reading_answers: dict[str, str]
    writing_answer: str = ""


def _all_review_passed(review: dict) -> bool:
    return bool(review) and all(
        isinstance(item, dict) and item.get("passed") is True
        for item in review.values()
    )


def _validation_block_reason(payload: dict) -> str | None:
    severity_by_id = {
        item.get("id"): item.get("severity")
        for item in payload.get("validation_rubric", [])
        if isinstance(item, dict)
    }
    failed = [
        item for item in payload.get("validation", {}).get("items", [])
        if isinstance(item, dict) and item.get("passed") is False
    ]
    critical = sum(severity_by_id.get(item.get("criterion_id")) == "critical" for item in failed)
    major = sum(severity_by_id.get(item.get("criterion_id")) == "major" for item in failed)
    if critical:
        return f"AI 검증의 치명 오류 {critical}건을 먼저 수정해야 합니다."
    if major >= 2:
        return f"AI 검증의 주요 오류 {major}건을 먼저 수정해야 합니다."
    return None


@app.get("/")
def root():
    return RedirectResponse("/teacher")


@app.get("/teacher")
def teacher_page():
    return FileResponse(STATIC / "teacher.html")


@app.get("/learner")
def learner_page():
    return FileResponse(STATIC / "learner.html")


@app.get("/api/config")
def config():
    categories = [{"id": row["id"], "label": row["label"]} for row in category_manifest()["categories"]]
    reading = [
        {"id": key, "label": value["label"], "short_label": value.get("short_label", ""),
         "description": value.get("description", "")}
        for key, value in reading_question_types().items()
    ]
    return {"categories": categories, "reading_types": reading}


@app.get("/api/health")
async def health():
    ok, message = await asyncio.to_thread(health_check, 30)
    return {"ok": ok, "message": message}


@app.post("/api/teacher/generate", status_code=202)
async def start_generation(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    teacher_name: str = Form(...), teacher_id: str = Form(...),
    grade: int = Form(...), category_id: str = Form(...),
):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, "PDF, TXT, MD 파일만 지원합니다.")
    content = await file.read()
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "파일이 비어 있거나 20MB를 초과합니다.")
    categories = {row["id"]: row["label"] for row in category_manifest()["categories"]}
    if category_id not in categories or grade not in range(1, 7):
        raise HTTPException(400, "등급 또는 카테고리가 올바르지 않습니다.")
    Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    path = Path(UPLOAD_DIR) / f"{uuid4().hex}-{Path(file.filename).name}"
    path.write_bytes(content)
    job_id = uuid4().hex
    graph = build_teacher_graph()
    _set_job(job_id, kind="teacher", status="queued", graph=graph, thread_id=uuid4().hex)
    state = initial_teacher_state(
        uploaded_filename=str(path), teacher_id=teacher_id, teacher_name=teacher_name,
        grade=grade, topic=categories[category_id], category_id=category_id,
        category_label=categories[category_id],
    )
    background.add_task(_run_teacher, job_id, state)
    return {"job_id": job_id}


@app.post("/api/teacher/jobs/{job_id}/passage-review", status_code=202)
def review_passage(job_id: str, body: PassageReview, background: BackgroundTasks):
    job = _jobs.get(job_id)
    if not job or job.get("stage") != "passage_review":
        raise HTTPException(404, "검토 대기 중인 지문 작업이 아닙니다.")
    if body.decision == "approve" and not body.reading_question_types:
        raise HTTPException(400, "읽기 문제 유형을 하나 이상 선택하세요.")
    if body.decision == "approve" and not _all_review_passed(body.approval_review):
        raise HTTPException(400, "모든 필수 지문 검토 항목을 승인해야 합니다.")
    if body.decision == "approve" and (reason := _validation_block_reason(job.get("payload", {}))):
        raise HTTPException(400, reason)
    if body.decision == "reject" and not body.note.strip():
        raise HTTPException(400, "재생성할 때 반영할 구체적인 수정 사유를 입력하세요.")
    background.add_task(_run_teacher, job_id, Command(resume=body.model_dump()))
    return {"job_id": job_id}


@app.post("/api/teacher/jobs/{job_id}/assessment-review", status_code=202)
def review_assessment(job_id: str, body: AssessmentReview, background: BackgroundTasks):
    job = _jobs.get(job_id)
    if not job or job.get("stage") != "assessment_review":
        raise HTTPException(404, "검토 대기 중인 문항 작업이 아닙니다.")
    item_count = len(job.get("payload", {}).get("reading_items", []))
    invalid = [index for index in body.reading_regeneration_indexes if index < 0 or index >= item_count]
    if invalid:
        raise HTTPException(400, "재생성할 읽기 문항 번호가 올바르지 않습니다.")
    if body.decision == "approve" and (body.reading_regeneration_indexes or body.writing_regeneration):
        raise HTTPException(400, "재생성 대상 문항이 있으면 최종 승인할 수 없습니다.")
    if body.decision == "approve" and not _all_review_passed(body.approval_review):
        raise HTTPException(400, "모든 필수 문항 검토 항목을 승인해야 합니다.")
    if body.decision == "approve" and (reason := _validation_block_reason(job.get("payload", {}))):
        raise HTTPException(400, reason)
    if body.decision == "reject" and not body.note.strip():
        raise HTTPException(400, "재생성할 문항의 수정 사유를 입력하세요.")
    background.add_task(_run_teacher, job_id, Command(resume=body.model_dump()))
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "작업을 찾을 수 없습니다.")
    return {key: value for key, value in job.items() if key not in {"graph", "thread_id"}}


@app.get("/api/learner/teachers")
def teachers(grade: int):
    return list_teachers(grade)


@app.get("/api/learner/tasks")
def tasks(grade: int, teacher_id: str):
    return list_tasks(grade, teacher_id)


@app.get("/api/learner/tasks/{task_id}")
def task(task_id: str):
    try:
        return load_public_task(task_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/learner/submit", status_code=202)
def submit(body: LearnerSubmission, background: BackgroundTasks):
    job_id = uuid4().hex
    _set_job(job_id, kind="learner", status="queued")
    background.add_task(_run_learner, job_id, body.model_dump())
    return {"job_id": job_id}
