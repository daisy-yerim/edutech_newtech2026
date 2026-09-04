from __future__ import annotations

import json

from app.core.llm import call_gemma_json
from app.services.category_profiles import sentence_type_profile
from app.services.rubrics import learner_rubric_for
from app.services.task_repository import load_task, save_submission


def load_assessment(state: dict) -> dict:
    public, grading = load_task(state["task_id"])
    return {"public_task": public, "grading_key": grading}


def grade_reading(state: dict) -> dict:
    answers = state.get("reading_answers", {})
    public_by_id = {item["id"]: item for item in state["public_task"]["reading_items"]}
    rows = []
    for key in state["grading_key"]["reading_items"]:
        submitted = answers.get(key["id"], "")
        rows.append({
            "id": key["id"], "question": public_by_id[key["id"]]["question"],
            "submitted_answer": submitted, "correct_answer": key["answer"],
            "correct": submitted == key["answer"], "explanation": key["explanation"],
        })
    count = sum(row["correct"] for row in rows)
    return {"reading_result": {
        "correct_count": count, "total_count": len(rows),
        "score": round(count / len(rows) * 100) if rows else 0, "items": rows,
    }}


def _empty_section(feedback: str) -> dict:
    return {"score": 0, "feedback": feedback, "evidence": [], "improvements": []}


def _zero_writing_result() -> dict:
    message = "쓰기 답안을 제출하지 않았습니다."
    return {
        "total_score": 0,
        "content_task_evaluation": _empty_section(message),
        "organization_evaluation": _empty_section(message),
        "language_use_evaluation": _empty_section(message),
        "scenario_diagnostic": {
            "scenario_id": "not_submitted",
            "label": "미제출",
            "reason": message,
        },
        "type_diagnostic": {"achieved": False, "feedback": message},
        "overall_feedback": "쓰기 답안을 입력해 주세요.",
        "rubric_version": 2,
    }


def _normalize_section(result: dict, name: str, maximum: int) -> None:
    section = result.get(name)
    if not isinstance(section, dict):
        section = _empty_section("채점 응답 형식 오류로 재확인이 필요합니다.")
        result[name] = section
    try:
        score = int(section.get("score", 0))
    except (TypeError, ValueError):
        score = 0
    section["score"] = max(0, min(maximum, score))
    section.setdefault("feedback", "")
    section.setdefault("evidence", [])
    section.setdefault("improvements", [])


def grade_writing(state: dict) -> dict:
    answer = state.get("writing_answer", "").strip()
    if not answer:
        return {"writing_result": _zero_writing_result()}

    public = state["public_task"]
    key = state["grading_key"]["writing"]
    sentence_type = key["sentence_type"]
    # 게시 시점의 예시답안·필수 내용은 근거로 사용하되 루브릭은 최신 연구 버전을 명시적으로 적용한다.
    rubric = learner_rubric_for(sentence_type, public["grade"])
    type_profile = sentence_type_profile(public["category_id"], sentence_type)
    prompt = f"""당신은 한국어 쓰기 평가 보조 채점자입니다. 아래 답안을 자문 전 연구용 분석적 루브릭으로 평가하세요.

[중요 원칙]
- 예시답안은 유일한 정답이 아니다. 표현이나 문장 유사도를 점수로 사용하지 않는다.
- 다른 관점이라도 과제를 충실히 수행하고 지문 근거가 타당하면 인정한다.
- 문장 유형은 별도 배점하지 않고 전개 구조의 '요구 기능 수행'에 반영한다.
- 연구용 루브릭의 cross_domain_scenarios와 independence_rules를 반드시 적용한다.
- 내용이 정확하고 문법만 틀린 답안은 내용 점수를 보존하고 언어 영역에서만 감점한다.
- 문법이 정확해도 내용이 틀린 답안은 언어 점수를 보존하고 내용 영역에서 감점한다.
- 문법 오류로 의미 자체가 달라진 경우에만 영향받은 내용 기준에도 반영하고 중복 영향의 이유를 근거에 밝힌다.
- 각 점수에는 답안에서 확인한 구체적 근거와 개선 방향을 제시한다.
- 정보가 부족하면 추측하지 말고 보수적으로 판정한다.

[문항]
{json.dumps(public['writing_task'], ensure_ascii=False)}
[교수자 승인 채점 자료]
{json.dumps(key, ensure_ascii=False)}
[연구용 루브릭]
{json.dumps(rubric, ensure_ascii=False)}
[카테고리·유형 참고 자료]
{json.dumps(type_profile, ensure_ascii=False)}
[학습자 답안]
{answer}

다음 JSON 객체만 출력하세요.
{{
  "content_task_evaluation": {{"score":0,"feedback":"0~30점 판정","evidence":[],"improvements":[]}},
  "organization_evaluation": {{"score":0,"feedback":"0~30점 판정","evidence":[],"improvements":[]}},
  "language_use_evaluation": {{"score":0,"feedback":"0~40점 판정","evidence":[],"improvements":[]}},
  "scenario_diagnostic": {{"scenario_id":"S1~S8 또는 mixed","label":"판정한 교차 시나리오","reason":"영역별 독립 판정 근거"}},
  "type_diagnostic": {{"achieved":true,"feedback":"{sentence_type} 기능 수행 진단"}},
  "overall_feedback":"강점과 가장 우선적인 개선점"
}}"""
    result = call_gemma_json(prompt)
    _normalize_section(result, "content_task_evaluation", 30)
    _normalize_section(result, "organization_evaluation", 30)
    _normalize_section(result, "language_use_evaluation", 40)
    if not isinstance(result.get("type_diagnostic"), dict):
        result["type_diagnostic"] = {"achieved": False, "feedback": "진단 형식 오류"}
    if not isinstance(result.get("scenario_diagnostic"), dict):
        result["scenario_diagnostic"] = {
            "scenario_id": "unknown",
            "label": "교차 시나리오 재확인 필요",
            "reason": "진단 형식 오류",
        }
    result["total_score"] = sum(result[name]["score"] for name in (
        "content_task_evaluation", "organization_evaluation", "language_use_evaluation"
    ))
    result["rubric_version"] = 2
    result["rubric_status"] = "provisional_pending_expert_review"
    return {"writing_result": result}


def combine_results(state: dict) -> dict:
    return {"final_result": {"reading": state["reading_result"], "writing": state["writing_result"]}}


def persist_submission(state: dict) -> dict:
    submission_id = save_submission(
        state["task_id"], state.get("reading_answers", {}),
        state.get("writing_answer", ""), state["final_result"],
    )
    return {"submission_id": submission_id}
