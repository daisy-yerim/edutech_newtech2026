"""두 번째 실험의 기계 검증 실패를 수정하고 재실험한다."""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.core.llm import call_gemma_json
from app.services.generation_standards import grade_requirements
from generate_diverse_validation_pack import OUT, SOURCES, TEXT_TYPES, prompt_for
from generate_grade_validation_pack import to_markdown, validate_pack

NUMBER_MARKS = {"①": 0, "②": 1, "③": 2, "④": 3}


def answer_index(answer: str) -> int | None:
    answer = str(answer).strip()
    if answer[:1] in NUMBER_MARKS:
        return NUMBER_MARKS[answer[:1]]
    match = re.match(r"^\s*([1-4])\s*[\.\)]?", answer)
    return int(match.group(1)) - 1 if match else None


def normalize_answers(output: dict) -> list[str]:
    changes = []
    for item_no, item in enumerate(output.get("reading_items", []), 1):
        choices = item.get("choices", [])
        answer = item.get("answer", "")
        if answer in choices:
            continue
        index = answer_index(answer)
        if index is not None and index < len(choices):
            old = answer
            item["answer"] = choices[index]
            changes.append(f"읽기 {item_no}: {old!r} -> {choices[index]!r}")
    return changes


def validation(output: dict, grade: int, source_index: int) -> dict:
    result = validate_pack(output, grade, (source_index + 1) % 3)
    result["checks"]["text_type_exact"] = (
        output.get("passage_text_type") == TEXT_TYPES[grade][source_index]
    )
    result["passed"] = all(result["checks"].values())
    return result


def correction_prompt(grade: int, source_index: int, failed: list[str], attempt: int) -> str:
    req = grade_requirements(grade)
    preferred_min = max(req["passage_chars"][0], int(req["passage_chars"][1] * .88))
    return prompt_for(grade, source_index) + f"""

[재실험 보정 지시 — {attempt}차]
이전 출력은 다음 자동 기준을 통과하지 못했습니다: {', '.join(failed)}.
- 지문은 반드시 공백 포함 {preferred_min}~{req['passage_chars'][1]}자로 충분히 길게 쓰세요.
- 예시답안은 반드시 공백 포함 {req['writing_chars'][0]}~{req['writing_chars'][1]}자로 쓰세요.
- 읽기 문항 수, 유형 순서, 선택지 4개를 정확히 지키세요.
- answer는 정답 choices 문자열 전체를 복사하세요. 번호만 출력하지 마세요.
- passage_text_type은 '{TEXT_TYPES[grade][source_index]}'을 글자 그대로 출력하세요.
출력 전 스스로 길이와 배열 개수를 점검한 뒤 완전한 JSON 객체 하나만 출력하세요.
"""


def main() -> None:
    raw_dir = OUT / "_raw_before_repair"
    raw_dir.mkdir(exist_ok=True)
    repaired_count = 0
    for path in sorted(OUT.glob("grade_*/experiment_*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        grade = int(record["grade"])
        source_index = int(record["experiment_no"]) - 1
        raw_path = raw_dir / f"grade_{grade}_experiment_{source_index + 1}.json"
        if not raw_path.exists():
            shutil.copy2(path, raw_path)

        history = record.setdefault("repair_history", [])
        changes = normalize_answers(record["output"])
        if changes:
            history.append({"attempt": "mechanical_answer_normalization", "changes": changes})
        result = validation(record["output"], grade, source_index)

        for attempt in range(1, 4):
            if result["passed"]:
                break
            failed = [key for key, value in result["checks"].items() if not value]
            # 정답 번호 표기만 남은 경우는 생성 전체를 다시 흔들지 않고 전문가 검토 대상으로 둔다.
            if set(failed) == {"answer_in_choices"}:
                break
            output = call_gemma_json(
                correction_prompt(grade, source_index, failed, attempt), temperature=.25
            )
            normalized = normalize_answers(output)
            next_result = validation(output, grade, source_index)
            history.append({
                "attempt": attempt, "failed_before": failed,
                "answer_normalizations": normalized,
                "passed_after": next_result["passed"],
                "checks_after": next_result["checks"],
            })
            record["output"] = output
            result = next_result

        record["mechanical_validation"] = result
        record["repair_status"] = "passed_after_repair" if result["passed"] else "needs_expert_review"
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        path.with_suffix(".md").write_text(to_markdown(record), encoding="utf-8")
        repaired_count += bool(history)
        print(
            f"{grade}-{source_index + 1}: "
            f"{'PASS' if result['passed'] else 'CHECK'} "
            f"(repairs={len(history)})",
            flush=True,
        )
    print(f"updated records: {repaired_count}", flush=True)


if __name__ == "__main__":
    main()
