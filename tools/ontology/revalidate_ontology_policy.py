"""Re-evaluate saved experiment results with the declarative ontology policy."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.services.ontology_rules import ontology_policy, validate_passage_ontology


def run(experiment: Path) -> dict:
    records = []
    for result_file in sorted(experiment.glob("*/grade_*/result.json")):
        saved = json.loads(result_file.read_text(encoding="utf-8"))
        final_round = saved["rounds"][-1]
        candidate = {
            "source_key": saved["source_key"],
            "grade": saved["grade"],
            "text_type": saved["text_type"],
            "source_terms": saved.get("source_terms", saved.get("essential_lexemes", [])),
            "passage": saved["generated_passage"],
            "vocabulary_audit": final_round["vocabulary_audit"],
        }
        validation = validate_passage_ontology(candidate)
        records.append({
            "source_key": saved["source_key"],
            "grade": saved["grade"],
            "previous_status": saved["status"],
            "policy_passed": validation["passed"],
            "failed_ids": validation["failed_ids"],
            "items": validation["items"],
        })
    output = {
        "schema_version": 1,
        "policy": ontology_policy(),
        "record_count": len(records),
        "pass_count": sum(x["policy_passed"] for x in records),
        "records": records,
    }
    (experiment / "ontology_policy_revalidation.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("experiment", type=Path)
    args = parser.parse_args()
    result = run(args.experiment.resolve())
    print(json.dumps({
        "record_count": result["record_count"],
        "pass_count": result["pass_count"],
    }, ensure_ascii=False))
