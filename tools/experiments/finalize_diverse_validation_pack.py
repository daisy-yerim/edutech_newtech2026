"""다양한 담화 형식의 두 번째 실험 묶음을 재검증하고 색인을 만든다."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from generate_diverse_validation_pack import OUT, SOURCES, TEXT_TYPES
from generate_grade_validation_pack import to_markdown, validate_pack


def main() -> None:
    rows = []
    for path in sorted(OUT.glob("grade_*/experiment_*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        source_index = record["experiment_no"] - 1
        record["mechanical_validation"] = validate_pack(
            record["output"], record["grade"], (source_index + 1) % 3
        )
        actual_type = record["output"].get("passage_text_type", "")
        record["mechanical_validation"]["checks"]["text_type_exact"] = (
            actual_type == record["assigned_text_type"]
        )
        record["mechanical_validation"]["passed"] = all(
            record["mechanical_validation"]["checks"].values()
        )
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        path.with_suffix(".md").write_text(to_markdown(record), encoding="utf-8")
        checks = record["mechanical_validation"]["checks"]
        rows.append({
            "grade": record["grade"], "experiment_no": record["experiment_no"],
            "source_id": record["source"]["id"], "assigned_text_type": record["assigned_text_type"],
            "actual_text_type": actual_type,
            "passage_chars": record["mechanical_validation"]["measured_passage_chars"],
            "sample_answer_chars": record["mechanical_validation"]["measured_sample_answer_chars"],
            "reading_items": len(record["output"].get("reading_items", [])),
            "mechanical_pass": record["mechanical_validation"]["passed"],
            "failed_checks": "; ".join(key for key, value in checks.items() if not value),
            "expert_status": "검토 전", "expert_notes": "",
        })

    with (OUT / "00_validation_summary.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    passed = sum(row["mechanical_pass"] for row in rows)
    sources = "\n".join(
        f"- {s['id']}: [{s['title']}]({s['url']}) — {s['agency']}, {s['published']}, {s['license']}"
        for s in SOURCES
    )
    types = "\n".join(
        f"- {grade}급: " + " / ".join(TEXT_TYPES[grade])
        for grade in range(1, 7)
    )
    readme = f"""# 새 원자료·다양한 지문 유형 1~6급 검증 묶음

## 구성

- 기존 묶음과 겹치지 않는 원자료 3건
- 6개 등급 × 지문 3개 = 18세트
- 읽기 지문 18개, 읽기 문항 81개, 쓰기 문항 18개
- 자동 검증 완전 통과: {passed}/18세트
- 최초 원출력은 `_raw_before_repair/`에 보존하고, 현재 결과에는 수정·재실험 이력을 기록

## 배정한 지문 유형

{types}

## 원자료

{sources}

세 페이지 모두 공공누리 제1유형이 표시된 정책브리핑 텍스트입니다. 사진·첨부파일은 사용하지 않았으며,
원문을 전재하지 않고 확인된 사실만 새 담화 형식으로 구성했습니다.

## 검토 방법

1. `00_validation_summary.csv`에서 배정 유형과 실제 출력 유형, 길이, 실패 사유를 비교합니다.
2. 같은 원자료가 등급별로 서로 다른 담화 형식에서 적절히 재구성됐는지 확인합니다.
3. 각 세트 Markdown 하단에 내용타당도와 수정 의견을 기록합니다.
4. 기계 검증 통과는 전문가 승인이나 저작권 법률 검토를 대신하지 않습니다.
"""
    (OUT / "README.md").write_text(readme, encoding="utf-8")

    review = """# 다양한 지문 유형 전문가 검증표

| 검토 항목 | 1 | 2 | 3 | 4 | 5 | 의견 |
|---|---:|---:|---:|---:|---:|---|
| 배정한 담화 형식 준수 | | | | | | |
| 담화 형식의 등급 적합성 | | | | | | |
| 어휘·문법 난이도 | | | | | | |
| 원자료 사실 충실성 | | | | | | |
| 읽기 문항의 다양성과 정답 유일성 | | | | | | |
| 쓰기 장르와 읽기 지문의 연계 | | | | | | |
| 쓰기 분량과 채점 가능성 | | | | | | |

- 검토자:
- 대상 세트:
- 종합 판정: 사용 가능 / 수정 후 사용 / 재개발
- 수정 의견:
"""
    (OUT / "01_expert_review_form.md").write_text(review, encoding="utf-8")


if __name__ == "__main__":
    main()
