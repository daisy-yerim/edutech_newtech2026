"""Create a small, editable view of a passage grade-loop experiment."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def failed_details(validation: dict) -> list[dict]:
    return [
        {
            "criterion_id": item.get("criterion_id", ""),
            "evidence": item.get("evidence", ""),
            "revision_instruction": item.get("revision_instruction", ""),
        }
        for item in validation.get("items", [])
        if item.get("passed") is False
    ]


def build(experiment: Path) -> Path:
    target = experiment / "easy_view"
    grades_dir = target / "grades"
    grades_dir.mkdir(parents=True, exist_ok=True)

    compact = []
    summary_lines = ["# 급수별 실험 결과", ""]
    for grade in range(1, 7):
        source = experiment / f"grade_{grade}.json"
        if not source.exists():
            continue
        record = json.loads(source.read_text(encoding="utf-8"))
        result = record["result"]
        compact.append({
            "grade": grade,
            "status": result["status"],
            "final_passage": result["generated_passage"],
            "rounds_used": result["rounds_used"],
            "failed_ids": result["failed_ids"],
            "failed_details": result.get("failed_details", []),
            "vocabulary_violations": result.get("vocabulary_violations", []),
            "blocked_unknown_nouns": result.get("blocked_unknown_nouns", []),
        })
        summary_lines.extend([
            f"## {grade}급 — {result['status']}",
            "",
            result["generated_passage"],
            "",
            f"- 생성·검증: {result['rounds_used']}회",
            f"- 실패 항목: {', '.join(result['failed_ids']) or '없음'}",
            "",
        ])

        rounds = []
        for item in record.get("rounds", []):
            audit = item.get("vocabulary_audit", {})
            validation = item.get("language_validation", {})
            rounds.append({
                "round": item["round"],
                "passed": item["passed"],
                "passage": item["passage"],
                "vocabulary_violations": audit.get("violations", []),
                "blocked_unknown_nouns": audit.get("blocked_unknown_nouns", []),
                "unknown_tokens": audit.get("unknown_tokens", []),
                "failed_ids": validation.get("failed_ids", []),
                "failed_details": failed_details(validation),
            })
        grade_file = {
            "guide": "final_passage가 최종 지문이고, rounds에는 최초 생성부터 모든 수정·검증 기록이 있습니다.",
            "grade": grade,
            "status": result["status"],
            "final_passage": result["generated_passage"],
            "rounds": rounds,
        }
        (grades_dir / f"grade_{grade}.json").write_text(
            json.dumps(grade_file, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    (target / "final_results.json").write_text(
        json.dumps(compact, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (target / "final_passages.md").write_text(
        "\n".join(summary_lines), encoding="utf-8"
    )
    report = experiment / "experiment_report.html"
    if report.exists():
        shutil.copy2(report, target / "report.html")
    readme = """# 쉬운 결과 폴더

이 폴더만 보면 됩니다.

1. `report.html` — 변경 기준과 전체 실험 결과를 화면으로 확인
2. `final_passages.md` — 1~6급 최종 지문을 가장 쉽게 읽기
3. `final_results.json` — 프로그램에서 사용할 간단한 최종 결과
4. `grades/grade_N.json` — 해당 급수의 최초 생성부터 수정·검증까지 확인

상위 폴더의 기존 JSON 파일은 원본 실험 기록이므로 수정하지 않고 보존했습니다.
"""
    (target / "README.md").write_text(readme, encoding="utf-8")
    return target


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("experiment", type=Path)
    args = parser.parse_args()
    print(build(args.experiment.resolve()))


if __name__ == "__main__":
    main()
