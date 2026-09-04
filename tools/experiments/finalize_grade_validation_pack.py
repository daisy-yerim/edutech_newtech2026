"""기존 실험 JSON을 재검증하고 전문가용 색인·CSV를 만든다."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from generate_grade_validation_pack import OUT, SOURCES, to_markdown, validate_pack


def main() -> None:
    rows = []
    for path in sorted(OUT.glob("grade_*/experiment_*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        record["mechanical_validation"] = validate_pack(
            record["output"], record["grade"], record["experiment_no"] - 1
        )
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        path.with_suffix(".md").write_text(to_markdown(record), encoding="utf-8")
        checks = record["mechanical_validation"]["checks"]
        rows.append({
            "grade": record["grade"],
            "experiment_no": record["experiment_no"],
            "source_id": record["source"]["id"],
            "passage_chars": record["mechanical_validation"]["measured_passage_chars"],
            "sample_answer_chars": record["mechanical_validation"]["measured_sample_answer_chars"],
            "reading_items": len(record["output"].get("reading_items", [])),
            "mechanical_pass": record["mechanical_validation"]["passed"],
            "failed_checks": "; ".join(key for key, value in checks.items() if not value),
            "expert_status": "검토 전",
            "expert_notes": "",
        })

    with (OUT / "00_validation_summary.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    passed = sum(row["mechanical_pass"] for row in rows)
    source_lines = "\n".join(
        f"- {source['id']}: [{source['title']}]({source['url']}) — "
        f"{source['agency']}, {source['published']}, {source['license']}"
        for source in SOURCES
    )
    grade_lines = "\n".join(
        f"- {grade}급: [폴더](grade_{grade}/) — 실험 3세트"
        for grade in range(1, 7)
    )
    readme = f"""# 한국어 1~6급 읽기·쓰기 전문가 검증 묶음

## 구성

- 총 18세트: 6개 등급 × 공통 원자료 3개
- 읽기 지문 18개, 읽기 문항 81개, 쓰기 문항 18개
- 각 세트는 검토용 Markdown과 원본·메타데이터 JSON으로 제공
- 전체 현황은 `00_validation_summary.csv`에서 필터링 가능
- 상태: 자문 전 연구용(`provisional_pending_expert_review`)

## 자동 검증 결과

- 완전 통과: {passed}/18세트
- 재검토 필요: {len(rows) - passed}/18세트
- 실패 표시는 실험 결과를 숨기지 않기 위한 것입니다. 주로 모델이 요구 길이를 짧게 생성하거나
  정답 문구를 선택지와 완전히 똑같이 복사하지 않은 경우입니다.
- 자동 검증 통과도 내용타당도·난이도·저작권의 전문가 승인을 뜻하지 않습니다.

## 등급별 폴더

{grade_lines}

## 원자료와 이용 조건

{source_lines}

모든 원자료는 페이지에 공공누리 제1유형이 표시된 정책브리핑 텍스트입니다.
제1유형은 출처표시 조건으로 상업·비상업 이용과 변경이 가능합니다. 사진·이미지·첨부파일은 사용하지 않았습니다.
지문은 원문을 전재하지 않고 위 자료의 사실 요약만 입력하여 새로 생성했습니다.

## 권장 전문가 검토 순서

1. `00_validation_summary.csv`에서 기계 검증 실패 사유를 확인합니다.
2. 같은 자료의 1~6급 지문을 나란히 보고 난이도의 단계성을 검토합니다.
3. 각 Markdown 하단의 체크란에 등급 적합성, 사실성, 정답 유일성, 쓰기 명료성을 기록합니다.
4. 정답 문구 불일치는 의미상 같은 경우에도 그대로 고치지 말고 전문가 판정 후 수정합니다.
5. 수정본은 원본 JSON을 보존한 채 별도 버전으로 관리합니다.
"""
    (OUT / "README.md").write_text(readme, encoding="utf-8")

    checklist = """# 전문가 검증 기록지

| 항목 | 1점 매우 부적합 | 2점 | 3점 보통 | 4점 | 5점 매우 적합 | 의견 |
|---|---:|---:|---:|---:|---:|---|
| 지문 주제의 등급 적합성 | | | | | | |
| 어휘·문법의 등급 적합성 | | | | | | |
| 문장·문단 복잡도의 단계성 | | | | | | |
| 원자료 사실 충실성 | | | | | | |
| 읽기 문항 유형 적합성 | | | | | | |
| 정답 유일성과 오답 기능 | | | | | | |
| 해설의 근거성과 교육성 | | | | | | |
| 쓰기 과제의 명료성 | | | | | | |
| 쓰기 분량·장르의 등급 적합성 | | | | | | |
| 예시답안·채점 메모의 활용성 | | | | | | |

- 검토자:
- 소속/전문 분야:
- 검토일:
- 대상 세트:
- 종합 판정: 사용 가능 / 수정 후 사용 / 재개발
- 핵심 수정 의견:
"""
    (OUT / "01_expert_review_form.md").write_text(checklist, encoding="utf-8")


if __name__ == "__main__":
    main()
