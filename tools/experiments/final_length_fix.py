"""재생성 3회 뒤 15자 부족한 단일 지문에 원자료 명시 사실을 최소 보충한다."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from generate_diverse_validation_pack import OUT, TEXT_TYPES
from generate_grade_validation_pack import to_markdown, validate_pack

PATH = OUT / "grade_3" / "experiment_3.json"
SOURCE_GROUNDED_SENTENCE = " 두 기관은 앞으로도 과제별 협력을 계속하기로 했다."


def main() -> None:
    record = json.loads(PATH.read_text(encoding="utf-8"))
    before = len(record["output"]["passage"])
    if before < record["grade_requirements"]["passage_chars"][0]:
        record["output"]["passage"] += SOURCE_GROUNDED_SENTENCE
        record.setdefault("repair_history", []).append({
            "attempt": "minimal_source_grounded_length_fix",
            "reason": f"최소 길이보다 {record['grade_requirements']['passage_chars'][0] - before}자 부족",
            "added_sentence": SOURCE_GROUNDED_SENTENCE.strip(),
        })
    result = validate_pack(record["output"], 3, 0)
    result["checks"]["text_type_exact"] = (
        record["output"].get("passage_text_type") == TEXT_TYPES[3][2]
    )
    result["passed"] = all(result["checks"].values())
    record["mechanical_validation"] = result
    record["repair_status"] = "passed_after_repair" if result["passed"] else "needs_expert_review"
    PATH.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    PATH.with_suffix(".md").write_text(to_markdown(record), encoding="utf-8")
    print(before, len(record["output"]["passage"]), result["passed"])


if __name__ == "__main__":
    main()
