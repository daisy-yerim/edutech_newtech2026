"""Revalidate saved ontology-loop passages and generate representative items."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.services.ontology_rules import validate_passage_ontology
from tools.experiments.run_ontology_validation_loop import generate_reading_items


SOURCE_EXPERIMENT = ROOT / "experiments/two_source_six_grades_ontology_loop_2026-08-12_rerun"
SOURCES = ("pet_restaurant", "energy_saving")


def question_checks(items: list[dict]) -> list[dict]:
    checks = []
    for item in items:
        failures = []
        choices = item.get("choices", [])
        if not item.get("question"):
            failures.append("QUESTION_MISSING")
        if len(choices) != 4:
            failures.append("CHOICE_COUNT")
        if item.get("answer") not in choices:
            failures.append("ANSWER_NOT_IN_CHOICES")
        if not item.get("explanation"):
            failures.append("EXPLANATION_MISSING")
        checks.append({
            "question_type": item.get("question_type", ""),
            "passed": not failures,
            "failed_ids": failures,
        })
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-experiment", type=Path, default=SOURCE_EXPERIMENT)
    parser.add_argument("--grades", type=int, nargs="+", default=[1, 3, 6])
    args = parser.parse_args()
    output = args.output.resolve()
    source_experiment = args.source_experiment.resolve()
    records = []
    for source_key in SOURCES:
        for grade in args.grades:
            unit = output / source_key / f"grade_{grade}"
            result_file = unit / "result.json"
            if result_file.exists():
                records.append(json.loads(result_file.read_text(encoding="utf-8")))
                print(f"{source_key} {grade}급: existing result", flush=True)
                continue
            source_file = source_experiment / source_key / f"grade_{grade}" / "result.json"
            saved = json.loads(source_file.read_text(encoding="utf-8"))
            final_round = saved["rounds"][-1]
            candidate = {
                "grade": grade,
                "passage": saved["generated_passage"],
                "source_key": source_key,
                "text_type": saved["text_type"],
                "source_terms": saved.get("source_terms", saved.get("essential_lexemes", [])),
                "essential_lexemes": saved.get("essential_lexemes", []),
                "vocabulary_audit": final_round.get("vocabulary_audit", {}),
            }
            ontology = validate_passage_ontology(candidate)
            print(f"{source_key} {grade}급: reading items", flush=True)
            items = generate_reading_items(saved["generated_passage"], grade)
            checks = question_checks(items)
            questions_passed = len(items) == 2 and all(x["passed"] for x in checks)
            record = {
                "schema_version": 1,
                "source_key": source_key,
                "grade": grade,
                "text_type": saved["text_type"],
                "source_experiment": str(source_file.relative_to(ROOT)),
                "generated_passage": saved["generated_passage"],
                "original_status": saved["status"],
                "rounds_used": saved["rounds_used"],
                "ontology_validation": ontology,
                "reading_items": items,
                "question_checks": checks,
                "question_status": "PASS" if questions_passed else "NEEDS_HUMAN_REVIEW",
                "overall_status": "PASS" if ontology["passed"] and questions_passed else "NEEDS_HUMAN_REVIEW",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            unit.mkdir(parents=True, exist_ok=True)
            result_file.write_text(
                json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            records.append(record)
    (output / "results.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "manifest.json").write_text(json.dumps({
        "schema_version": 1,
        "design": "two sources x representative grades 1, 3, 6 x two reading item types",
        "source_experiment": str(SOURCE_EXPERIMENT.relative_to(ROOT)),
        "record_count": len(records),
        "records": [{
            "source_key": x["source_key"], "grade": x["grade"],
            "overall_status": x["overall_status"],
            "question_status": x["question_status"],
            "ontology_passed": x["ontology_validation"]["passed"],
        } for x in records],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output / "manifest.json")


if __name__ == "__main__":
    main()
