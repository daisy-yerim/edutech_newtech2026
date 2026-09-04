"""Load the three independent teacher-side rubric families."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "criteria" / "rubrics"
FILES = {
    "generation": ROOT / "generation" / "teacher_generation.json",
    "validation": ROOT / "validation" / "ai_validation.json",
    "approval": ROOT / "approval" / "teacher_approval.json",
}


@lru_cache(maxsize=3)
def teacher_rubric(kind: str) -> dict:
    if kind not in FILES:
        raise ValueError(f"알 수 없는 루브릭 종류: {kind}")
    return json.loads(FILES[kind].read_text(encoding="utf-8"))


def rubric_section(kind: str, stage: str) -> list[dict]:
    if stage not in {"passage", "assessment"}:
        raise ValueError(f"알 수 없는 검토 단계: {stage}")
    return teacher_rubric(kind)[stage]


def rubric_prompt(kind: str, stage: str) -> str:
    return json.dumps(rubric_section(kind, stage), ensure_ascii=False, indent=2)
