"""Export existing grade-loop JSON files as a human-readable Markdown report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def display_data(record: dict) -> dict:
    if isinstance(record.get("result"), dict):
        return record["result"]
    audit = record.get("final_vocabulary_audit", {})
    validation = record.get("final_validation", {})
    return {
        "generated_passage": record.get("final_passage", ""),
        "status": record.get("status", "UNKNOWN"),
        "rounds_used": len(record.get("rounds", [])),
        "failed_ids": validation.get("failed_ids", []),
        "vocabulary_violations": [
            item.get("word", "") for item in audit.get("violations", [])
        ],
        "blocked_unknown_nouns": [
            item.get("word", "") for item in audit.get("blocked_unknown_nouns", [])
        ],
    }


def export_report(folder: Path) -> Path:
    records = []
    for path in sorted(folder.glob("grade_*.json")):
        records.append(json.loads(path.read_text(encoding="utf-8")))
    if not records:
        raise FileNotFoundError(f"급수별 JSON 결과가 없습니다: {folder}")

    lines = ["# 급수별 최종 생성 지문", ""]
    for record in records:
        display = display_data(record)
        lines.extend([
            f"## {record['grade']}급 — {display['status']}",
            "",
            display["generated_passage"],
            "",
            f"- 생성·검증 횟수: {display['rounds_used']}회",
            f"- 실패 항목: {', '.join(display['failed_ids']) or '없음'}",
            f"- 등급 초과 어휘: {', '.join(display['vocabulary_violations']) or '없음'}",
            f"- 차단된 미등록 일반명사: {', '.join(display['blocked_unknown_nouns']) or '없음'}",
            "",
        ])
    output = folder / "PASSAGES.md"
    output.write_text("\n".join(lines), encoding="utf-8")
    compact = [
        {"grade": record["grade"], **display_data(record)} for record in records
    ]
    (folder / "passages_only.json").write_text(
        json.dumps(compact, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    print(export_report(args.folder).resolve())


if __name__ == "__main__":
    main()
