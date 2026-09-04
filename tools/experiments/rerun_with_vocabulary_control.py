"""18개 실험 지문에 등급 초과 어휘 교체를 적용하고 문항을 다시 생성한다."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.core.llm import call_gemma_json
from app.services.generation_standards import grade_requirements, standard_prompt
from app.services.vocabulary_control import audit_vocabulary, simplify_passage_vocabulary
from generate_diverse_validation_pack import OUT, TEXT_TYPES
from generate_grade_validation_pack import TYPE_ROTATION, to_markdown, validate_pack
from repair_diverse_validation_pack import normalize_answers


def assessment_prompt(record: dict) -> str:
    grade = int(record["grade"])
    source_index = int(record["experiment_no"]) - 1
    req = grade_requirements(grade)
    types = TYPE_ROTATION[(source_index + 1) % 3][:req["reading_item_count"]]
    passage = record["output"]["passage"]
    return f"""당신은 한국어 읽기·쓰기 평가 문항 개발자입니다.

[목표 등급]
{grade}급
{standard_prompt(grade, "writing")}

[어휘 교체를 마친 승인 지문]
{passage}

[읽기 문항 유형 — 순서대로]
{json.dumps(types, ensure_ascii=False)}

[절대 조건]
- 모든 질문·정답·해설·필수 내용은 위 지문만으로 해결 가능해야 합니다.
- 읽기 문항은 지정 유형별 1개, 선택지 4개, 정답 1개입니다.
- answer는 choices의 정답 문자열 전체를 글자 그대로 복사하세요.
- 쓰기 예시답안은 공백 포함 {req['writing_chars'][0]}~{req['writing_chars'][1]}자입니다.
- 예시답안은 유일 정답이 아니며 다양한 타당 답안을 허용하세요.

다음 JSON 객체 하나만 출력하세요.
{{
  "reading_items":[{{
    "type":"지정 유형","question":"질문",
    "choices":["① ...","② ...","③ ...","④ ..."],
    "answer":"선택지 전체","explanation":"지문 근거와 오답 배제 이유"
  }}],
  "writing_task":{{
    "genre":"등급에 맞는 장르","instruction":"쓰기 지시문",
    "conditions":["분량","필수 내용","요구 기능"],
    "required_content":["채점 핵심 요소"],
    "sample_answer":"참고 답안","scoring_notes":"등급별 채점 메모"
  }}
}}"""


def mechanical(record: dict) -> dict:
    grade = int(record["grade"])
    source_index = int(record["experiment_no"]) - 1
    result = validate_pack(record["output"], grade, (source_index + 1) % 3)
    result["checks"]["text_type_exact"] = (
        record["output"].get("passage_text_type") == TEXT_TYPES[grade][source_index]
    )
    result["checks"]["vocabulary_grade"] = (
        record["vocabulary_audit"]["violation_count"] == 0
    )
    result["passed"] = all(result["checks"].values())
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grades", nargs="*", type=int, default=list(range(1, 7)))
    parser.add_argument("--resume-current", action="store_true")
    args = parser.parse_args()
    backup = OUT / "_before_vocabulary_control"
    backup.mkdir(exist_ok=True)
    for path in sorted(OUT.glob("grade_*/experiment_*.json")):
        current_record = json.loads(path.read_text(encoding="utf-8"))
        grade = int(current_record["grade"])
        if grade not in args.grades:
            continue
        if (
            current_record.get("vocabulary_control_status") == "passed"
            and current_record.get("mechanical_validation", {}).get("passed")
            and current_record.get("vocabulary_audit", {}).get("engine") == "kiwipiepy"
        ):
            print(f"{grade}-{current_record['experiment_no']}: already PASS", flush=True)
            continue
        source_index = int(current_record["experiment_no"]) - 1
        backup_path = backup / f"grade_{grade}_experiment_{source_index + 1}.json"
        # 재실행 시 어휘 교체 전 원본에서 다시 시작하여 이전의 잘못된 교체를 누적하지 않는다.
        source_path = path if args.resume_current else (
            backup_path if backup_path.exists() else path
        )
        record = json.loads(source_path.read_text(encoding="utf-8"))
        grade = int(record["grade"])
        source_index = int(record["experiment_no"]) - 1
        if not backup_path.exists():
            shutil.copy2(path, backup_path)
        req = grade_requirements(grade)
        facts = "\n".join(
            fact for fact in record["source"].get("facts", [])
            if "공공누리" not in fact and "라이선스" not in fact
        )
        exemptions = {
            word for word in ("식품의약품안전처", "행정중심복합도시건설청", "우주항공청", "국방부")
            if word in record["output"]["passage"]
        }
        if record["source"]["id"] == "N1":
            exemptions.update({"반려동물"})
        elif record["source"]["id"] == "N2":
            exemptions.update({"행복", "도시"})
        elif record["source"]["id"] == "N3":
            exemptions.update({"우주", "위성", "국방부", "우주항공청", "발사체", "안보"})
        before = record["output"]["passage"]
        revised, audit, history = simplify_passage_vocabulary(
            before, grade, facts,
            req["passage_chars"][0], req["passage_chars"][1],
            max_rounds=1 if args.resume_current else (4 if grade <= 2 else 3),
            exempt_words=exemptions,
        )
        record["output"]["passage"] = revised
        record["vocabulary_audit"] = audit
        record["vocabulary_revision_history"] = history
        record["vocabulary_control"] = {
            "before_passage": before,
            "before_audit": audit_vocabulary(before, grade, exemptions),
            "exempt_words": sorted(exemptions),
            "after_passage": revised,
            "after_audit": audit,
        }

        # 지문이 바뀌었으면 기존 문항의 근거가 달라지므로 읽기·쓰기 전체를 다시 만든다.
        if revised != before and audit["violation_count"] == 0:
            for attempt in range(1, 4):
                generated = call_gemma_json(assessment_prompt(record), temperature=.25)
                record["output"]["reading_items"] = generated.get("reading_items", [])
                record["output"]["writing_task"] = generated.get("writing_task", {})
                normalize_answers(record["output"])
                record["mechanical_validation"] = mechanical(record)
                if record["mechanical_validation"]["passed"]:
                    break
        else:
            record["mechanical_validation"] = mechanical(record)

        record["vocabulary_control_status"] = (
            "passed" if audit["violation_count"] == 0 else "needs_expert_review"
        )
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        path.with_suffix(".md").write_text(to_markdown(record), encoding="utf-8")
        print(
            f"{grade}-{source_index+1}: vocab "
            f"{record['vocabulary_control']['before_audit']['violation_count']}"
            f"->{audit['violation_count']}, revisions={len(history)}, "
            f"mechanical={'PASS' if record['mechanical_validation']['passed'] else 'CHECK'}",
            flush=True,
        )


if __name__ == "__main__":
    main()
