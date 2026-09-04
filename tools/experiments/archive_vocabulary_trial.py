"""부분 어휘 교체 실험을 보관하고 검증 묶음 본본은 교체 전 상태로 복원한다."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "experiments" / "expert_validation_diverse_2026-07"
BACKUP = OUT / "_before_vocabulary_control"
TRIAL = OUT / "_vocabulary_control_trial"


def main() -> None:
    TRIAL.mkdir(exist_ok=True)
    restored = 0
    for backup in BACKUP.glob("grade_*_experiment_*.json"):
        parts = backup.stem.split("_")
        grade, experiment = parts[1], parts[3]
        target = OUT / f"grade_{grade}" / f"experiment_{experiment}.json"
        markdown = target.with_suffix(".md")
        if target.exists():
            shutil.copy2(target, TRIAL / backup.name)
        shutil.copy2(backup, target)
        if markdown.exists():
            shutil.copy2(markdown, TRIAL / f"grade_{grade}_experiment_{experiment}.md")
        restored += 1
    print(f"restored={restored}")


if __name__ == "__main__":
    main()
