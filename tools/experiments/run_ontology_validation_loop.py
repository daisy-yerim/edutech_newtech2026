"""Generate two standard source passages with ontology checks inside the repair loop."""

from __future__ import annotations

import argparse
from difflib import SequenceMatcher
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.services.generation_standards import grade_requirements
from app.services.vocabulary_control import audit_vocabulary, clean_revised_passage
from app.core.llm import call_gemma, call_gemma_json
from app.services.ontology_rules import validate_passage_ontology
from app.teacher.nodes import validate_passage
from app.workflow.nodes.passage_node import passage_node
from tools.experiments.run_passage_grade_loop import (
    BEGINNER_KEYWORD_CONTEXTS,
    BEGINNER_SOURCE_KEYWORDS,
    repair_note,
    source_text,
)


SOURCES = [
    ("pet_restaurant", ROOT / "data/sources/government/pet_restaurant/source_facts.json"),
    ("energy_saving", ROOT / "data/sources/government/energy_saving/source_facts.json"),
]
MAX_ROUNDS = 4
TYPE_BY_GRADE = {
    1: "개인 문자", 2: "안내문", 3: "짧은 기사",
    4: "사회적 설명문", 5: "보고서", 6: "전문 자료",
}
ESSENTIAL_LEXEMES = {
    "pet_restaurant": {
        3: {"반려동물", "접종"}, 4: {"반려동물", "접종"},
        5: {"반려동물", "접종", "식품위생법"},
        6: {"반려동물", "접종", "식품위생법"},
    },
    "energy_saving": {
        3: {"에너지", "승용차"}, 4: {"에너지", "승용차"},
        5: {"에너지", "승용차"}, 6: {"에너지", "승용차"},
    },
}
QUESTION_TYPES = ["main_idea", "content_match"]


def normalize_reading_item(item: dict) -> dict:
    """Normalize common local-model choice/answer numbering without changing content."""
    normalized = dict(item)
    choices = [str(choice).strip() for choice in item.get("choices", [])]
    # Some models emit ["1", "choice one", "2", "choice two", ...].
    if len(choices) == 8 and choices[::2] == ["1", "2", "3", "4"]:
        choices = choices[1::2]
    answer = str(item.get("answer", "")).strip()
    if answer in {"1", "2", "3", "4"} and len(choices) == 4:
        answer = choices[int(answer) - 1]
    elif answer not in choices and len(choices) == 4:
        # Snap a near-identical answer paraphrase back to the exact choice.
        ranked = sorted(
            ((SequenceMatcher(None, answer, choice).ratio(), choice) for choice in choices),
            reverse=True,
        )
        if ranked and ranked[0][0] >= 0.72:
            answer = ranked[0][1]
    normalized["choices"] = choices
    normalized["answer"] = answer
    return normalized


def generate_reading_items(passage: str, grade: int) -> list[dict]:
    """Generate the two representative items in one bounded model call."""
    prompt = f"""다음 {grade}급 한국어 지문으로 읽기 문항 2개를 만드세요.

[지문]
{passage}

[문항 유형]
1. main_idea: 중심 생각 고르기
2. content_match: 내용 일치 또는 불일치 고르기

각 문항은 선택지 4개, 선택지 원문과 정확히 같은 정답, 지문 근거를 밝힌 해설을 포함해야 합니다.
지문에 없는 사실을 정답 근거로 추가하지 마세요. 다음 JSON 객체만 출력하세요.
{{"items":[{{"question_type":"main_idea","question":"질문","choices":["1","2","3","4"],"answer":"정답 선택지","explanation":"해설"}},{{"question_type":"content_match","question":"질문","choices":["1","2","3","4"],"answer":"정답 선택지","explanation":"해설"}}]}}
"""
    raw = call_gemma_json(prompt)
    items = raw.get("items", [])
    return [normalize_reading_item(item) for item in items if isinstance(item, dict)]


def strip_model_heading(text: str) -> str:
    """Remove a model-added Markdown/plain title from learner passage output."""
    final_markers = list(re.finditer(
        r"(?im)^\s*(?:[-]{3,}\s*)?(?:\*\*)?\s*최종\s+(?:출력물|지문|결과)"
        r"(?:\s*\([^\n]*\))?\s*:?\s*(?:\*\*)?\s*$",
        text,
    ))
    if final_markers:
        text = text[final_markers[-1].end():]
    text = re.split(r"(?m)^\s*\*?\s*\(?(?:참고|설명)\s*:", text, maxsplit=1)[0]
    text = re.sub(r"(?m)^\s*-{3,}\s*$", "", text)
    text = re.sub(r"\s*\(\s*\d+자[^)]*\)\s*$", "", text.strip())
    lines = text.strip().splitlines()
    if not lines:
        return ""
    first = lines[0].strip()
    if re.fullmatch(r"\*\*.+\*\*", first) or first.startswith("#"):
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines.pop(0)
    return "\n".join(lines).strip()


def compress_to_target(passage: str, grade: int, source: str, text_type: str) -> str:
    low, high = grade_requirements(grade)["passage_chars"]
    if low <= len(passage) <= high:
        return passage
    action = "압축" if len(passage) > high else "보완"
    length_rule = (
        "반복, 제목, 평가적 결론, 덜 중요한 예시부터 삭제하세요."
        if len(passage) > high else
        "원문에 이미 있는 사실 중 빠진 핵심 행동·시간·장소를 쉬운 문장으로 보완하세요."
    )
    prompt = f"""다음 한국어 {grade}급 {text_type} 지문을 공백 포함 {low}~{high}자로 {action}하세요.
- 원문의 사실·수치·주체·인과를 바꾸거나 새 사실을 추가하지 마세요.
- 문맥의 시작→전개→결과를 유지하세요.
- {length_rule}
- 목표 급수보다 어려운 새 단어를 추가하지 마세요.
- 제목, 글자 수 계산, 수정 설명, 참고, 전후 비교 없이 최종 지문만 출력하세요.

[사실 근거]
{source}

[지문]
{passage}
"""
    return strip_model_heading(clean_revised_passage(call_gemma(prompt, temperature=0.1)))


def _legacy_ontology_validate(candidate: dict) -> dict:
    """Apply only relations declared by the formal ontology schema."""
    grade = int(candidate["grade"])
    passage = candidate["passage"]
    low, high = grade_requirements(grade)["passage_chars"]
    vocabulary = candidate.get("vocabulary_audit", {})
    essential = set(candidate.get("essential_lexemes", []))
    violations = [x for x in vocabulary.get("violations", []) if x["word"] not in essential]
    permitted = [x for x in vocabulary.get("violations", []) if x["word"] in essential]
    blocked = vocabulary.get("blocked_unknown_tokens", [])
    items = []

    length_passed = low <= len(passage) <= high
    items.append({
        "criterion_id": "O-VAL-LENGTH",
        "passed": length_passed,
        "evidence": f"공백 포함 {len(passage)}자, {grade}급 목표 {low}~{high}자",
        "revision_instruction": (
            f"핵심 사실과 문맥 연결을 유지하면서 공백 포함 {low}~{high}자로 줄이세요. "
            "반복 설명과 평가적 결론을 먼저 삭제하세요."
        ),
    })
    items.append({
        "criterion_id": "O-VAL-SOURCE-TERM",
        "passed": True,
        "evidence": (
            "원문 필수어 예외 없음" if not permitted else
            "원문 사실 관계로 선언된 필수어: " + ", ".join(
                f"{x['word']}({x['grade']}급)" for x in permitted
            )
        ),
        "revision_instruction": "필수어는 원문 의미로만 사용하고 가까운 문장에서 쉽게 설명하세요.",
    })
    vocab_passed = not violations and not blocked
    labels = [f"{x['word']}({x['grade']}급)" for x in violations]
    labels += [f"{x['word']}(미등록)" for x in blocked]
    items.append({
        "criterion_id": "O-VAL-GRADE-RESOURCE",
        "passed": vocab_passed,
        "evidence": "목표 급수 초과·미등록 어휘 없음" if vocab_passed else ", ".join(labels),
        "revision_instruction": (
            f"다음 어휘를 {grade}급 이하 등록 표현으로 바꾸되 원문 사실을 삭제하거나 "
            f"새 사실을 추가하지 마세요: {', '.join(labels)}"
        ),
    })
    relation_passed = bool(candidate.get("text_type")) and 1 <= grade <= 6
    items.append({
        "criterion_id": "O-VAL-REQUIRED-RELATIONS",
        "passed": relation_passed,
        "evidence": f"Passage→TARGETS_GRADE→{grade}급, 텍스트 유형={candidate.get('text_type', '')}",
        "revision_instruction": "지문 목표 급수와 텍스트 유형 관계를 복구하세요.",
    })
    failed = [x["criterion_id"] for x in items if not x["passed"]]
    return {"passed": not failed, "failed_ids": failed, "items": items}


def ontology_validate(candidate: dict) -> dict:
    return validate_passage_ontology(candidate)


def feedback(validation: dict) -> str:
    return "\n".join(
        f"- {x['criterion_id']}: {x['revision_instruction']}"
        for x in validation["items"] if not x["passed"]
    )


def run_one(
    key: str, source: dict, output: Path, grade: int, text_type: str,
    ontology_mode: str = "diagnostic",
) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    beginner = grade in {1, 2}
    keyword = BEGINNER_SOURCE_KEYWORDS.get(source["id"], {}).get(grade, "") if beginner else ""
    keyword_context = BEGINNER_KEYWORD_CONTEXTS.get(source["id"], {}).get(grade, "") if beginner else ""
    grounded_source = source_text(source)
    generation_source = (
        f"원자료에서 고른 필수 핵심어: {keyword}. 핵심어의 원문 의미: {keyword_context}. "
        "이 핵심어 하나로 TOPIK I의 쉬운 일상 장면을 자유롭게 개작합니다."
        if beginner else grounded_source
    )
    state = {
        "source_key": key,
        "grade": grade,
        "topic": source["title"],
        "category_id": "social",
        "category_label": "사회",
        "text_type": text_type,
        "source_mode": "beginner_free_adaptation" if beginner else "source_grounded",
        "source_text": generation_source,
        "required_keyword": keyword,
        "required_keyword_context": keyword_context,
        "essential_lexemes": sorted(ESSENTIAL_LEXEMES.get(key, {}).get(grade, set())),
        "source_terms": sorted(
            set(ESSENTIAL_LEXEMES.get(key, {}).get(grade, set())) |
            ({keyword} if keyword else set())
        ),
        "reject_note": "",
        "passage_round": 1,
    }
    rounds = []
    for round_no in range(1, MAX_ROUNDS + 1):
        print(f"{key}: generation round {round_no}", flush=True)
        generated = passage_node({**state, "round_no": round_no})
        passage = strip_model_heading(generated["passage"])
        passage = compress_to_target(passage, grade, generation_source, text_type)
        generated["passage"] = passage
        generated["vocabulary_audit"] = audit_vocabulary(
            passage, grade, set(state.get("source_terms", []))
        )
        candidate = {**state, **generated}
        print(f"{key}: AI validation round {round_no}", flush=True)
        ai_validation = validate_passage(candidate)["passage_validation"]
        ontology_validation = ontology_validate(candidate)
        passed = bool(ai_validation.get("passed")) and (
            ontology_validation["passed"] if ontology_mode == "gate" else True
        )
        record = {
            "round": round_no,
            "passage": candidate["passage"],
            "chars": len(candidate["passage"]),
            "vocabulary_audit": candidate.get("vocabulary_audit", {}),
            "ai_validation": ai_validation,
            "ontology_validation": ontology_validation,
            "passed": passed,
        }
        rounds.append(record)
        (output / f"round_{round_no}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if passed:
            break
        state = {
            **candidate,
            "reject_note": "\n".join(filter(None, [
                "[기존 AI 검증 수정]", repair_note(ai_validation),
                "[온톨로지 검증 수정]" if ontology_mode == "gate" else "",
                feedback(ontology_validation) if ontology_mode == "gate" else "",
            ])),
            "passage_round": round_no + 1,
        }
    final = rounds[-1]
    print(f"{key}: reading item generation", flush=True)
    reading_items = generate_reading_items(final["passage"], grade)
    question_checks = []
    for item in reading_items:
        choices = item.get("choices", [])
        failed = []
        if not item.get("question"):
            failed.append("QUESTION_MISSING")
        if len(choices) != 4:
            failed.append("CHOICE_COUNT")
        if item.get("answer") not in choices:
            failed.append("ANSWER_NOT_IN_CHOICES")
        if not item.get("explanation"):
            failed.append("EXPLANATION_MISSING")
        question_checks.append({
            "question_type": item.get("question_type", ""),
            "passed": not failed,
            "failed_ids": failed,
        })
    questions_passed = len(reading_items) == len(QUESTION_TYPES) and all(
        item["passed"] for item in question_checks
    )
    passage_status = "PASS" if final["passed"] else "NEEDS_HUMAN_REVIEW"
    result = {
        "schema_version": 1,
        "experiment": "ontology_in_validation_loop",
        "ontology_mode": ontology_mode,
        "source_key": key,
        "grade": grade,
        "text_type": text_type,
        "essential_lexemes": state["essential_lexemes"],
        "required_keyword": keyword,
        "source_terms": sorted(set(state["essential_lexemes"]) | ({keyword} if keyword else set())),
        "status": "PASS" if final["passed"] and questions_passed else "NEEDS_HUMAN_REVIEW",
        "passage_status": passage_status,
        "question_status": "PASS" if questions_passed else "NEEDS_HUMAN_REVIEW",
        "rounds_used": len(rounds),
        "generated_passage": final["passage"],
        "final_ai_validation": final["ai_validation"],
        "final_ontology_validation": final["ontology_validation"],
        "reading_items": reading_items,
        "question_checks": question_checks,
        "rounds": rounds,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (output / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--grades", type=int, nargs="+", default=list(range(1, 7)))
    parser.add_argument(
        "--ontology-mode", choices=["diagnostic", "gate"], default="diagnostic",
        help="diagnostic은 생성 후 기록만 하고, gate는 실패를 수정 루프에 반영합니다.",
    )
    args = parser.parse_args()
    base = args.output.resolve()
    results = []
    for key, meta in SOURCES:
        for grade in args.grades:
            text_type = TYPE_BY_GRADE[grade]
            unit = base / key / f"grade_{grade}"
            result_file = unit / "result.json"
            if result_file.exists():
                result = json.loads(result_file.read_text(encoding="utf-8"))
            else:
                result = run_one(
                    key, json.loads(meta.read_text(encoding="utf-8")), unit,
                    grade, text_type, args.ontology_mode,
                )
            results.append(result)
    compact = [{
        "grade": x["grade"], "source_key": x["source_key"],
        "generated_passage": x["generated_passage"], "status": x["status"],
        "passage_status": x.get("passage_status", x["status"]),
        "question_status": x.get("question_status", "NOT_RUN"),
        "reading_items": x.get("reading_items", []),
        "rounds_used": x["rounds_used"],
        "text_type": x["text_type"],
        "essential_lexemes": x.get("source_terms", x["essential_lexemes"]),
        "failed_ids": x["final_ontology_validation"]["failed_ids"],
        "vocabulary_violations": [], "blocked_unknown_nouns": [],
    } for x in results]
    (base / "passages_only.json").write_text(
        json.dumps(compact, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (base / "manifest.json").write_text(json.dumps({
        "schema_version": 1, "expected_count": len(SOURCES) * len(args.grades),
        "loop": (
            "generation -> AI validation -> repair; ontology post-generation diagnostic"
            if args.ontology_mode == "diagnostic" else
            "generation -> AI validation + ontology validation -> repair"
        ),
        "ontology_mode": args.ontology_mode,
        "records": [{"source_key": x["source_key"], "status": x["status"],
                     "passage_status": x.get("passage_status", x["status"]),
                     "question_status": x.get("question_status", "NOT_RUN"),
                     "grade": x["grade"], "text_type": x["text_type"],
                     "rounds": x["rounds_used"]} for x in results],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(base / "manifest.json")


if __name__ == "__main__":
    main()
