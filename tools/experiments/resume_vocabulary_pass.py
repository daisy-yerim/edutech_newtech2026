"""규칙 보정으로 어휘 위반이 0이 된 현재 세트의 문항을 새 지문 기준으로 다시 생성한다."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.core.llm import call_gemma_json
from app.services.vocabulary_control import audit_vocabulary
from generate_diverse_validation_pack import OUT
from generate_grade_validation_pack import to_markdown
from repair_diverse_validation_pack import normalize_answers
from rerun_with_vocabulary_control import assessment_prompt, mechanical


def main() -> None:
    for path in sorted(OUT.glob("grade_*/experiment_*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if not record.get("vocabulary_control"):
            continue
        exemptions = set(record["vocabulary_control"].get("exempt_words", []))
        audit = audit_vocabulary(record["output"]["passage"], int(record["grade"]), exemptions)
        if audit["violation_count"] or record.get("vocabulary_control_status") == "passed":
            continue
        record["vocabulary_audit"] = audit
        for _ in range(3):
            generated = call_gemma_json(assessment_prompt(record), temperature=.25)
            record["output"]["reading_items"] = generated.get("reading_items", [])
            record["output"]["writing_task"] = generated.get("writing_task", {})
            normalize_answers(record["output"])
            record["mechanical_validation"] = mechanical(record)
            if record["mechanical_validation"]["passed"]:
                break
        record["vocabulary_control_status"] = "passed"
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        path.with_suffix(".md").write_text(to_markdown(record), encoding="utf-8")
        print(record["grade"], record["experiment_no"], record["mechanical_validation"]["passed"], flush=True)


if __name__ == "__main__":
    main()
