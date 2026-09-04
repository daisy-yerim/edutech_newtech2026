"""Data-driven ontology validation used by the application and experiments.

The policy file is the source of truth. This module is the external execution
engine for constraints that plain SQLite and the local model cannot execute.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.services.generation_standards import grade_requirements


ROOT = Path(__file__).resolve().parents[2]
POLICY_FILE = ROOT / "ontology/policy/validation_policy.json"


@lru_cache(maxsize=1)
def ontology_policy() -> dict:
    return json.loads(POLICY_FILE.read_text(encoding="utf-8"))


def _result(rule: dict, passed: bool, evidence: str, instruction: str) -> dict:
    return {
        "criterion_id": rule["id"],
        "severity": rule["severity"],
        "passed": passed,
        "evidence": evidence,
        "revision_instruction": instruction,
        "policy_kind": rule["kind"],
    }


def validate_passage_ontology(candidate: dict[str, Any]) -> dict:
    """Evaluate passage constraints declared in validation_policy.json."""
    grade = int(candidate["grade"])
    passage = str(candidate.get("passage", ""))
    audit = candidate.get("vocabulary_audit", {})
    source_terms = set(candidate.get("source_terms") or candidate.get("essential_lexemes", []))
    used_lemmas = {
        item["word"] for item in audit.get("known_lexemes", [])
        if isinstance(item, dict) and item.get("word")
    }
    # Existing audit schema always exposes violations; compliant source terms may
    # be recovered by exact occurrence when the audit does not list all lemmas.
    used_lemmas |= {
        term for term in source_terms if term and term in passage
    }
    items = []
    for rule in ontology_policy()["rules"]:
        kind = rule["kind"]
        if kind == "passage_length_from_grade_requirement":
            low, high = grade_requirements(grade)["passage_chars"]
            passed = low <= len(passage) <= high
            items.append(_result(
                rule, passed, f"공백 포함 {len(passage)}자, {grade}급 목표 {low}~{high}자",
                f"원문 사실과 문맥을 유지하면서 공백 포함 {low}~{high}자로 조정하세요.",
            ))
        elif kind == "lexeme_grade_not_above_target_unless_required":
            violations = [
                x for x in audit.get("violations", [])
                if x.get("word") not in source_terms
            ]
            blocked = audit.get("blocked_unknown_tokens", [])
            labels = [f"{x['word']}({x['grade']}급)" for x in violations]
            labels += [f"{x['word']}(미등록)" for x in blocked]
            items.append(_result(
                rule, not labels,
                "목표 급수 초과·미등록 어휘 없음" if not labels else ", ".join(labels),
                f"다음 어휘를 {grade}급 이하 등록 표현으로 바꾸세요: {', '.join(labels)}",
            ))
        elif kind == "required_source_term_must_be_used":
            missing = sorted(source_terms - used_lemmas)
            items.append(_result(
                rule, not missing,
                "선언된 원문 필수어를 모두 사용함" if not missing else "누락: " + ", ".join(missing),
                "원문 의미를 유지해 다음 필수어를 실제 지문에 사용하세요: " + ", ".join(missing),
            ))
        elif kind == "passage_required_relations":
            counts = {
                "TARGETS_GRADE": 1 if 1 <= grade <= 6 else 0,
                "GROUNDED_IN": 1 if candidate.get("source_key") else 0,
                "REALIZES_TEXT_TYPE": 1 if candidate.get("text_type") else 0,
            }
            failed = [
                name for name, minimum in rule["min_count"].items()
                if counts.get(name, 0) < minimum or counts.get(name, 0) > rule["max_count"][name]
            ]
            items.append(_result(
                rule, not failed,
                ", ".join(f"{name}={count}" for name, count in counts.items()),
                "누락되거나 중복된 지문 관계를 복구하세요: " + ", ".join(failed),
            ))
        else:
            raise ValueError(f"지원하지 않는 온톨로지 규칙 kind: {kind}")

    failed = [
        item["criterion_id"] for item in items
        if not item["passed"] and item["severity"] == "Violation"
    ]
    return {
        "policy_schema_version": ontology_policy()["schema_version"],
        "passed": not failed,
        "failed_ids": failed,
        "items": items,
    }
