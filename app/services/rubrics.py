"""자문 전 연구용 학습자 쓰기 루브릭 로더."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.services.generation_standards import grade_requirements

ROOT = Path(__file__).resolve().parent.parent.parent
LEARNER_DIR = ROOT / "data" / "criteria" / "rubrics" / "learner"


def _read(filename: str) -> dict:
    return json.loads((LEARNER_DIR / filename).read_text(encoding="utf-8"))


def _validated(filename: str) -> dict:
    rubric = _read(filename)
    total = sum(item["weight"] for item in rubric["criteria"])
    if total != rubric["max_score"]:
        raise ValueError(f"{filename} 배점 오류: {total} != {rubric['max_score']}")
    return rubric


@lru_cache(maxsize=1)
def content_task_rubric() -> dict:
    return _validated("reference_answer.json")


@lru_cache(maxsize=1)
def organization_rubric() -> dict:
    return _validated("writing_quality.json")


@lru_cache(maxsize=1)
def language_use_rubric() -> dict:
    return _validated("language_use.json")


@lru_cache(maxsize=1)
def scoring_scenarios() -> dict:
    return _read("scoring_scenarios.json")


def learner_rubric_for(sentence_type: str = "writing", grade: int | None = None) -> dict:
    content = content_task_rubric()
    organization = organization_rubric()
    language = language_use_rubric()
    total = content["max_score"] + organization["max_score"] + language["max_score"]
    if total != 100:
        raise ValueError(f"학습자 쓰기 루브릭 총점 오류: {total}")
    result = {
        "id": "learner_writing_provisional_v2",
        "version": 2,
        "status": "provisional_pending_expert_review",
        "basis": [
            "한국어 표준 교육과정(문화체육관광부고시 제2020-54호)",
            "TOPIK II 쓰기 공개 채점 영역",
            "CEFR 2020 및 ACTFL 2024 비교 구성개념",
        ],
        "source_registry": "data/criteria/source_registry.json",
        "weight_policy": "30/30/40은 공식 배점이 아닌 프로젝트 운영값이며 채점자 검증 전 잠정 적용",
        "max_score": 100,
        "content_task_evaluation": content,
        "organization_evaluation": organization,
        "language_use_evaluation": language,
        "cross_domain_scenarios": scoring_scenarios(),
    }
    if grade is not None:
        requirements = grade_requirements(grade)
        result["target_grade"] = grade
        result["grade_specific_expectations"] = {
            "writing_chars": requirements["writing_chars"],
            "writing_genres": requirements["writing_genres"],
            "required_structure": requirements["required_structure"],
            "scoring_expectation": requirements["scoring_expectation"],
        }
    return result


# 이전 코드가 호출하던 이름을 유지한다.
reference_answer_rubric = content_task_rubric
writing_quality_rubric = organization_rubric
