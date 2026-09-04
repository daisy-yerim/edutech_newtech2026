"""등급별 어휘·문법을 생성물 전체에서 감사하고 제한적으로 교정한다."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from app.core.llm import call_gemma_json
from app.services.dictionary import prompt_grammar
from app.services.vocabulary_control import (
    allowed_vocabulary_sample,
    audit_vocabulary,
)

TEXT_FIELDS = {
    "question", "choices", "answer", "explanation", "instruction", "conditions",
    "sample_answer", "required_content", "target_vocabulary", "target_grammar",
}


def _text_entries(value: Any, path: str = "") -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key in TEXT_FIELDS:
                entries.extend(_all_strings(child, child_path))
            elif isinstance(child, (dict, list)):
                entries.extend(_text_entries(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            entries.extend(_text_entries(child, f"{path}[{index}]"))
    return entries


def _all_strings(value: Any, path: str) -> list[tuple[str, str]]:
    if isinstance(value, str):
        return [(path, value)]
    if isinstance(value, list):
        result = []
        for index, child in enumerate(value):
            result.extend(_all_strings(child, f"{path}[{index}]"))
        return result
    if isinstance(value, dict):
        result = []
        for key, child in value.items():
            result.extend(_all_strings(child, f"{path}.{key}"))
        return result
    return []


def audit_language(document: Any, target_grade: int, task_type: str) -> dict:
    """텍스트 필드별 초과 어휘와 적용한 문법 통제 프로필을 반환한다."""
    fields = []
    total_violations = 0
    for path, text in _text_entries(document):
        audit = audit_vocabulary(text, target_grade)
        if audit["violation_count"]:
            fields.append({
                "path": path,
                "violations": audit["violations"],
                "unknown_tokens": audit["unknown_tokens"],
            })
            total_violations += audit["violation_count"]
    grammar_text, grammar_count = prompt_grammar(task_type, target_grade)
    return {
        "target_grade": target_grade,
        "vocabulary": {
            "violation_count": total_violations,
            "fields": fields,
        },
        "grammar": {
            "mode": "grade_profile_constrained",
            "task_type": task_type,
            "recommended_count": grammar_count,
            "recommended_forms": grammar_text,
            "deterministic_postcheck": False,
            "note": "문법은 형태 중의성 때문에 등급 프로필로 생성·교정을 제한하고 AI 검증과 교수자 검토를 병행합니다.",
        },
    }


def _reading_structure_valid(before: Any, after: Any) -> bool:
    if not isinstance(before, list) or not isinstance(after, list) or len(before) != len(after):
        return False
    for old, new in zip(before, after):
        if not isinstance(old, dict) or not isinstance(new, dict):
            return False
        if old.get("question_type") != new.get("question_type"):
            return False
        choices = new.get("choices")
        if not isinstance(choices, list) or len(choices) != 4:
            return False
        if new.get("answer") not in choices:
            return False
    return True


def _writing_structure_valid(before: Any, after: Any) -> bool:
    return (
        isinstance(before, dict)
        and isinstance(after, dict)
        and set(before).issubset(after)
        and all(after.get(key) for key in ("instruction", "sample_answer", "required_content"))
        and isinstance(after.get("conditions"), list)
        and isinstance(after.get("required_content"), list)
    )


def adjust_language_document(
    document: Any,
    target_grade: int,
    task_type: str,
    document_kind: str,
    source_text: str = "",
    max_rounds: int = 2,
) -> tuple[Any, dict, list[dict]]:
    """초과 어휘가 있으면 사실·문항 구조를 보존한 채 해당 표현만 교정한다."""
    current = deepcopy(document)
    history: list[dict] = []
    for round_no in range(1, max_rounds + 1):
        audit = audit_language(current, target_grade, task_type)
        violations = audit["vocabulary"]["fields"]
        if not violations:
            return current, audit, history
        grammar_text = audit["grammar"]["recommended_forms"]
        allowed_words = ", ".join(allowed_vocabulary_sample(target_grade, limit=180))
        prompt = f"""당신은 한국어 평가 문항의 등급별 언어 교정자입니다.

[목표]
아래 {document_kind}의 표시된 초과 어휘를 {target_grade}급 이하 표현으로 바꾸고,
문장 구조도 {target_grade}급 권장 문법 범위에서 자연스럽게 다듬으세요.

[초과 어휘 위치]
{json.dumps(violations, ensure_ascii=False)}

[사용 가능한 쉬운 어휘 예시]
{allowed_words}

[권장 문법]
{grammar_text or "목표 급수의 기본 문법"}

[사실 확인용 원자료]
{source_text}

[교정 대상 JSON]
{json.dumps(current, ensure_ascii=False)}

[보존 규칙]
- JSON 최상위 형태와 모든 필드 이름을 그대로 유지하세요.
- 문항 수, 문항 유형, 선택지 수는 바꾸지 마세요.
- 정답은 교정된 선택지 문자열 중 하나와 완전히 같아야 합니다.
- 숫자, 날짜, 고유명사, 사실, 정답의 의미와 오답의 역할을 바꾸지 마세요.
- 내용을 추가하거나 삭제하지 말고 어휘·문법 표현만 교정하세요.
- JSON 객체 하나만 출력하세요.

{{"document": 교정된_JSON}}"""
        raw = call_gemma_json(prompt, temperature=0.1)
        revised = raw.get("document")
        valid = (
            _reading_structure_valid(current, revised)
            if document_kind == "읽기 문항"
            else _writing_structure_valid(current, revised)
        )
        if not valid:
            history.append({
                "round": round_no,
                "accepted": False,
                "reason": "교정 결과가 원래 문항 구조 또는 정답 일관성을 훼손함",
                "before_violation_count": audit["vocabulary"]["violation_count"],
            })
            break
        next_audit = audit_language(revised, target_grade, task_type)
        accepted = (
            next_audit["vocabulary"]["violation_count"]
            < audit["vocabulary"]["violation_count"]
        )
        history.append({
            "round": round_no,
            "accepted": accepted,
            "before_violation_count": audit["vocabulary"]["violation_count"],
            "after_violation_count": next_audit["vocabulary"]["violation_count"],
        })
        if not accepted:
            break
        current = revised
    return current, audit_language(current, target_grade, task_type), history
