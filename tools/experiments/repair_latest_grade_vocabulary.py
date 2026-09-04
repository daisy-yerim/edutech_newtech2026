"""Repair the latest 12 passages against grade vocabulary, without reusing stale item approval."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.services.generation_standards import grade_requirements
from app.services.ontology_rules import validate_passage_ontology
from app.services.vocabulary_control import (
    audit_vocabulary,
    polish_passage_naturalness,
    simplify_passage_vocabulary,
)
from tools.experiments.run_ontology_validation_loop import ESSENTIAL_LEXEMES, SOURCES
from tools.experiments.run_passage_grade_loop import source_text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_paths = dict(SOURCES)
    records = []
    for key, path in SOURCES:
        source = json.loads(path.read_text(encoding="utf-8"))
        grounded = source_text(source)
        for grade in range(1, 7):
            src = args.input / key / f"grade_{grade}" / "result.json"
            result = json.loads(src.read_text(encoding="utf-8"))
            before = result["generated_passage"]
            exemptions = set(ESSENTIAL_LEXEMES.get(key, {}).get(grade, set()))
            if grade in {1, 2} and result.get("required_keyword"):
                exemptions.add(result["required_keyword"])
            req = grade_requirements(grade)
            before_audit = audit_vocabulary(before, grade, exemptions)
            revised, after_audit, history = simplify_passage_vocabulary(
                before,
                grade,
                grounded,
                req["passage_chars"][0],
                req["passage_chars"][1],
                max_rounds=3 if grade <= 2 else 2 if grade <= 5 else 0,
                exempt_words=exemptions,
            )
            polished, polished_audit, naturalness_revision = polish_passage_naturalness(
                revised,
                grade,
                grounded,
                req["passage_chars"][0],
                req["passage_chars"][1],
                exempt_words=exemptions,
            )
            revised_issue_count = (
                after_audit.get("violation_count", 0)
                + after_audit.get("blocked_unknown_token_count", 0)
            )
            polished_issue_count = (
                polished_audit.get("violation_count", 0)
                + polished_audit.get("blocked_unknown_token_count", 0)
            )
            naturalness_accepted = (
                polished != revised and polished_issue_count <= revised_issue_count
            )
            if naturalness_accepted:
                revised, after_audit = polished, polished_audit
            repaired = deepcopy(result)
            repaired["experiment"] = "topik_economy_grade_vocabulary_repair"
            repaired["generated_passage"] = revised
            repaired["source_terms"] = sorted(exemptions)
            repaired["vocabulary_repair"] = {
                "before_passage": before,
                "after_passage": revised,
                "before_audit": before_audit,
                "after_audit": after_audit,
                "history": history,
                "naturalness_revision": naturalness_revision,
                "naturalness_accepted": naturalness_accepted,
            }
            candidate = {
                "grade": grade,
                "passage": revised,
                "text_type": repaired.get("text_type", "읽기 지문"),
                "vocabulary_audit": after_audit,
                "essential_lexemes": sorted(exemptions),
            }
            repaired["final_ontology_validation"] = validate_passage_ontology(candidate)
            changed = revised != before
            repaired["question_status"] = "NEEDS_REGENERATION" if changed else result.get("question_status")
            repaired["status"] = (
                "PASS" if not changed and result.get("status") == "PASS"
                else "NEEDS_HUMAN_REVIEW"
            )
            unit = args.output / key / f"grade_{grade}"
            unit.mkdir(parents=True, exist_ok=True)
            (unit / "result.json").write_text(
                json.dumps(repaired, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            records.append({
                "source_key": key,
                "grade": grade,
                "changed": changed,
                "before_violation_count": before_audit.get("violation_count", 0),
                "after_violation_count": after_audit.get("violation_count", 0),
                "before_unknown_count": before_audit.get("blocked_unknown_token_count", 0),
                "after_unknown_count": after_audit.get("blocked_unknown_token_count", 0),
            })
            print(
                f"{key} {grade}: {before_audit.get('violation_count', 0)}"
                f"->{after_audit.get('violation_count', 0)}, changed={changed}",
                flush=True,
            )
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "manifest.json").write_text(
        json.dumps({"records": records}, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
