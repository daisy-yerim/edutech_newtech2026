"""SQLite repository used by both the teacher and learner graphs."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from uuid import uuid4

from app.services.database import connect
from app.services.rubrics import learner_rubric_for


def _safe_id(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z가-힣_-]+", "-", value.strip()).strip("-")
    return cleaned or "teacher"


def _loads(value: str) -> dict | list:
    return json.loads(value)


def publish_assessment(state: dict) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    task_id = f"task-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}"
    teacher_id = _safe_id(state.get("teacher_id", "teacher-demo"))
    teacher_name = state.get("teacher_name", teacher_id)
    writing = state.get("writing_task", {})
    writing_public = {
        "sentence_type": state["writing_sentence_type"],
        "instruction": writing.get("instruction", ""),
        "conditions": writing.get("conditions", []),
    }
    writing_grading = {
        "sentence_type": state["writing_sentence_type"],
        "sample_answer": writing.get("sample_answer", ""),
        "explanation": writing.get("explanation", ""),
        "required_content": writing.get("required_content", []),
        "target_vocabulary": writing.get("target_vocabulary", []),
        "target_grammar": writing.get("target_grammar", []),
        "scoring_guide": writing.get("scoring_guide", {}),
        "rubric": learner_rubric_for(state["writing_sentence_type"]),
    }
    audit = {
        "passage_validation": state.get("passage_validation", {}),
        "assessment_validation": state.get("validation", {}),
        "passage_approval_review": state.get("passage_approval_review", {}),
        "assessment_approval_review": state.get("assessment_approval_review", {}),
        "review_history": state.get("review_history", []),
    }
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO teachers VALUES (?, ?, ?)",
            (teacher_id, teacher_name, now),
        )
        conn.execute(
            """INSERT INTO assessments
            (task_id,teacher_id,grade,topic,category_id,category_label,passage,
             writing_public_json,writing_grading_json,audit_json,created_at,published)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,1)""",
            (task_id, teacher_id, state["grade"], state.get("topic", ""),
             state["category_id"], state.get("category_label", state["category_id"]),
             state["passage"], json.dumps(writing_public, ensure_ascii=False),
             json.dumps(writing_grading, ensure_ascii=False),
             json.dumps(audit, ensure_ascii=False), now),
        )
        for position, item in enumerate(state.get("reading_items", []), 1):
            conn.execute(
                "INSERT INTO reading_items VALUES (?,?,?,?,?,?,?,?)",
                (task_id, f"r{position}", position, item.get("question_type", ""),
                 item.get("question", ""), json.dumps(item.get("choices", []), ensure_ascii=False),
                 item.get("answer", ""), item.get("explanation", "")),
            )
    return load_public_task(task_id)


def _public_from_row(conn, row) -> dict:
    items = conn.execute(
        "SELECT * FROM reading_items WHERE task_id=? ORDER BY position", (row["task_id"],)
    ).fetchall()
    return {
        "schema_version": 2, "task_id": row["task_id"],
        "teacher_id": row["teacher_id"], "teacher_name": row["teacher_name"],
        "grade": row["grade"], "topic": row["topic"],
        "category_id": row["category_id"], "category_label": row["category_label"],
        "created_at": row["created_at"], "passage": row["passage"],
        "reading_items": [{
            "id": item["item_id"], "question_type": item["question_type"],
            "question": item["question"], "choices": _loads(item["choices_json"]),
        } for item in items],
        "writing_task": _loads(row["writing_public_json"]),
    }


def load_public_task(task_id: str) -> dict:
    with connect() as conn:
        row = conn.execute("""SELECT a.*,t.teacher_name FROM assessments a
            JOIN teachers t USING(teacher_id) WHERE task_id=? AND published=1""", (task_id,)).fetchone()
        if row is None:
            raise FileNotFoundError(f"게시 문항을 찾을 수 없습니다: {task_id}")
        return _public_from_row(conn, row)


def list_published() -> list[dict]:
    with connect() as conn:
        rows = conn.execute("""SELECT a.*,t.teacher_name FROM assessments a
            JOIN teachers t USING(teacher_id) WHERE published=1 ORDER BY created_at DESC""").fetchall()
        return [_public_from_row(conn, row) for row in rows]


def list_teachers(grade: int | None = None) -> list[dict]:
    sql = """SELECT DISTINCT t.teacher_id,t.teacher_name FROM teachers t
             JOIN assessments a USING(teacher_id) WHERE a.published=1"""
    params = []
    if grade is not None:
        sql += " AND a.grade=?"
        params.append(grade)
    sql += " ORDER BY t.teacher_name"
    with connect() as conn:
        return [dict(row) for row in conn.execute(sql, params)]


def list_tasks(grade: int, teacher_id: str) -> list[dict]:
    return [row for row in list_published() if row["grade"] == grade and row["teacher_id"] == teacher_id]


def load_task(task_id: str) -> tuple[dict, dict]:
    public = load_public_task(task_id)
    with connect() as conn:
        assessment = conn.execute(
            "SELECT writing_grading_json FROM assessments WHERE task_id=?", (task_id,)
        ).fetchone()
        items = conn.execute(
            "SELECT item_id,answer,explanation FROM reading_items WHERE task_id=? ORDER BY position",
            (task_id,),
        ).fetchall()
    grading = {
        "task_id": task_id,
        "reading_items": [dict(row) | {"id": row["item_id"]} for row in items],
        "writing": _loads(assessment["writing_grading_json"]),
    }
    for item in grading["reading_items"]:
        item.pop("item_id", None)
    return public, grading


def save_submission(task_id: str, reading_answers: dict, writing_answer: str, result: dict, learner_id: str = "learner-demo") -> str:
    submission_id = f"submission-{uuid4().hex}"
    with connect() as conn:
        conn.execute(
            "INSERT INTO submissions VALUES (?,?,?,?,?,?,?)",
            (submission_id, task_id, learner_id,
             json.dumps(reading_answers, ensure_ascii=False), writing_answer,
             json.dumps(result, ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
        )
    return submission_id
