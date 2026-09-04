"""SKA 읽기·쓰기 생성 기준과 읽기 문항 유형 자산 로더."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RESOURCES_DIR = PROJECT_ROOT / "data" / "criteria"
SKA_FILE = RESOURCES_DIR / "standards" / "ska_generation.json"
GRADE_REQUIREMENTS_FILE = RESOURCES_DIR / "standards" / "grade_requirements.json"
TOPIK1_PROFILE_FILE = RESOURCES_DIR / "standards" / "topik1_adaptation_profile.json"
BAND_PROFILE_FILE = RESOURCES_DIR / "standards" / "band_generation_profiles.json"
QUESTION_TYPE_DIR = RESOURCES_DIR / "reading_question_types"
QUESTION_TYPE_FILE = QUESTION_TYPE_DIR / "manifest.json"


def _read_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"생성 기준 파일이 없습니다: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def ska_standards() -> dict:
    return _read_json(SKA_FILE)


def standard_for(grade: int, skill: str) -> dict:
    if grade not in range(1, 7):
        raise ValueError("등급은 1~6이어야 합니다.")
    if skill not in {"reading", "writing"}:
        raise ValueError("skill은 reading 또는 writing이어야 합니다.")
    grade_spec = ska_standards()["grades"][str(grade)]
    return {
        "grade": grade,
        "ska_score": grade_spec["ska_score"],
        "band": grade_spec["band"],
        **grade_spec[skill],
        "requirements": grade_requirements(grade),
    }


@lru_cache(maxsize=6)
def grade_requirements(grade: int) -> dict:
    if grade not in range(1, 7):
        raise ValueError("등급은 1~6이어야 합니다.")
    return _read_json(GRADE_REQUIREMENTS_FILE)["grades"][str(grade)]


@lru_cache(maxsize=1)
def topik1_adaptation_profile() -> dict:
    return _read_json(TOPIK1_PROFILE_FILE)


@lru_cache(maxsize=1)
def band_generation_profiles() -> dict:
    return _read_json(BAND_PROFILE_FILE)


@lru_cache(maxsize=6)
def band_profile(grade: int) -> dict:
    if grade not in range(1, 7):
        raise ValueError("등급은 1~6이어야 합니다.")
    band_id = "beginner" if grade <= 2 else "intermediate" if grade <= 4 else "advanced"
    return {"id": band_id, **band_generation_profiles()["bands"][band_id]}


def standard_prompt(grade: int, skill: str) -> str:
    spec = standard_for(grade, skill)
    req = spec["requirements"]
    band = band_profile(grade)
    lines = [
        f"구간 프로필: {band['label']} ({band['grades'][0]}~{band['grades'][-1]}급)",
        f"구간 내용 범위: {band['content_scope']}",
        "구간 텍스트 설계: " + "; ".join(band["text_design"]),
        "구간 이해 부담: " + "; ".join(band["reading_load"]),
        "구간 어휘·문체: " + "; ".join(band["vocabulary_and_style"]),
        "구간 검증 초점: " + "; ".join(band["validation_focus"]),
        f"SKA 대응 구간: {spec['ska_score']} ({spec['band']})",
        f"권장 주제: {', '.join(spec['topics'])}",
        f"권장 텍스트 유형: {', '.join(spec['text_types'])}",
        f"수행 기능: {', '.join(spec['functions'])}",
        f"언어 복잡도: {spec['complexity']}",
        f"구조: {req['required_structure']}",
    ]
    if skill == "reading":
        lines.extend([
            f"지문 목표 길이: 공백 포함 {req['passage_chars'][0]}~{req['passage_chars'][1]}자",
            "목표 길이 안에서 하나의 중심 내용만 완결하고, 분량을 채우기 위한 새 사례·배경 설명은 추가하지 않음",
            f"문단 수: {req['paragraphs'][0]}~{req['paragraphs'][1]}개",
            f"평균 문장 길이 상한: 약 {req['sentence_chars_average_max']}자",
            f"읽기 초점: {', '.join(req['reading_focus'])}",
            f"권장 문항 수: {req['reading_item_count']}개",
        ])
        if grade in {1, 2}:
            topik_profile = topik1_adaptation_profile()["grade_profiles"][str(grade)]
            lines.extend([
                "TOPIK I 기출 기반 개작 원칙: 기출 문장을 복제하지 않고 언어 부담과 정보 관계만 참고",
                f"문장 수 권장: {topik_profile['passage_sentences'][0]}~{topik_profile['passage_sentences'][1]}개",
                f"문장 설계: {'; '.join(topik_profile['sentence_design'])}",
                f"허용 정보 관계: {', '.join(topik_profile['information_relations'])}",
                f"어휘 통제: {'; '.join(topik_profile['vocabulary_policy'])}",
                f"피해야 할 요소: {', '.join(topik_profile['avoid'])}",
            ])
    else:
        lines.extend([
            f"답안 길이: 공백 포함 {req['writing_chars'][0]}~{req['writing_chars'][1]}자",
            f"권장 장르: {', '.join(req['writing_genres'])}",
            f"등급별 채점 기대: {req['scoring_expectation']}",
        ])
    return "\n".join(lines)


@lru_cache(maxsize=1)
def reading_question_manifest() -> dict:
    return _read_json(QUESTION_TYPE_FILE)


def reading_question_types() -> dict:
    return reading_question_manifest()["types"]


def question_type_spec(type_id: str) -> dict:
    types = reading_question_types()
    if type_id not in types:
        raise ValueError(f"없는 읽기 문항 유형입니다: {type_id}. 사용 가능: {list(types)}")
    spec = dict(types[type_id])
    spec["image_path"] = str(QUESTION_TYPE_DIR / spec["image"])
    return spec


def question_types_prompt(type_ids: list[str]) -> str:
    blocks = []
    for index, type_id in enumerate(type_ids, start=1):
        spec = question_type_spec(type_id)
        rules = "\n".join(f"  - {rule}" for rule in spec["construction_rules"])
        blocks.append(
            f"{index}. {spec['label']} ({type_id})\n"
            f"{spec['prompt_instruction']}\n작성 규칙:\n{rules}"
        )
    return "\n\n".join(blocks)
