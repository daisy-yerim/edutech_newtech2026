"""Build the canonical report artifact for the ontology question experiment."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


SOURCE_LABELS = {
    "pet_restaurant": "반려동물 동반 음식점",
    "energy_saving": "민간기업 에너지 절약",
}


def esc_md(value: object) -> str:
    return str(value).replace("|", "\\|")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", type=Path, required=True)
    args = parser.parse_args()
    experiment = args.experiment.resolve()
    records = json.loads((experiment / "results.json").read_text(encoding="utf-8"))
    records.sort(key=lambda x: (x["source_key"], x["grade"]))
    generated_at = datetime.now(timezone.utc).isoformat()
    total = len(records)
    ontology_pass = sum(x["ontology_validation"]["passed"] for x in records)
    question_pass = sum(x["question_status"] == "PASS" for x in records)
    overall_pass = sum(x["overall_status"] == "PASS" for x in records)
    total_items = sum(len(x["reading_items"]) for x in records)

    summary_rows = []
    for record in records:
        failed = record["ontology_validation"].get("failed_ids", [])
        summary_rows.append({
            "source": SOURCE_LABELS[record["source_key"]],
            "source_key": record["source_key"],
            "grade": record["grade"],
            "text_type": record["text_type"],
            "rounds": record["rounds_used"],
            "ontology_pass": 1 if record["ontology_validation"]["passed"] else 0,
            "ontology_status": "PASS" if record["ontology_validation"]["passed"] else "검토 필요",
            "question_status": record["question_status"].replace("NEEDS_HUMAN_REVIEW", "검토 필요"),
            "overall_status": record["overall_status"].replace("NEEDS_HUMAN_REVIEW", "검토 필요"),
            "failed_rules": ", ".join(failed) or "없음",
            "question_count": len(record["reading_items"]),
        })

    report_db = experiment / "report_data.sqlite"
    query_sql = """SELECT source, source_key, grade, text_type, rounds, ontology_pass,
ontology_status, question_status, overall_status, failed_rules, question_count
FROM experiment_summary
ORDER BY source_key, grade"""
    with sqlite3.connect(report_db) as conn:
        conn.execute("DROP TABLE IF EXISTS experiment_summary")
        conn.execute("""CREATE TABLE experiment_summary (
            source TEXT, source_key TEXT, grade INTEGER, text_type TEXT,
            rounds INTEGER, ontology_pass INTEGER, ontology_status TEXT,
            question_status TEXT, overall_status TEXT, failed_rules TEXT,
            question_count INTEGER
        )""")
        conn.executemany(
            "INSERT INTO experiment_summary VALUES (:source, :source_key, :grade, :text_type, :rounds, :ontology_pass, :ontology_status, :question_status, :overall_status, :failed_rules, :question_count)",
            summary_rows,
        )
        cursor = conn.execute(query_sql)
        columns = [item[0] for item in cursor.description]
        summary_rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

    metric_rows = [{
        "total_combinations": total,
        "total_items": total_items,
        "ontology_pass": ontology_pass,
        "question_pass": question_pass,
        "overall_pass": overall_pass,
    }]
    summary_table_md = [
        "| 원문 | 급수 | 유형 | 회차 | 온톨로지 | 문항 | 종합 | 실패 규칙 |",
        "|---|---:|---|---:|---|---|---|---|",
    ]
    for row in summary_rows:
        summary_table_md.append(
            f"| {esc_md(row['source'])} | {row['grade']} | {esc_md(row['text_type'])} | "
            f"{row['rounds']} | {row['ontology_status']} | {row['question_status']} | "
            f"{row['overall_status']} | {esc_md(row['failed_rules'])} |"
        )
    source_id = "experiment-results"
    blocks = [
        {"id": "technical-summary", "type": "markdown", "sourceId": source_id,
         "body": "## 기술 요약\n\n"
                 f"두 원문을 1~6급에 적용한 **{total}개 지문**과 **{total_items}개 읽기 문항**을 검토했다. "
                 f"현재 온톨로지 자동 통과는 **{ontology_pass}/{total}**, 문항 구조 통과는 **{question_pass}/{total}**, "
                 f"종합 통과는 **{overall_pass}/{total}**다. 자동 검증은 전문가 품질 판정을 대체하지 않으며, "
                 "검토 필요 결과는 아래 규칙별 근거와 문항 원문으로 확인해야 한다."},
        {"id": "key-findings", "type": "markdown", "sourceId": source_id,
         "body": "## 급수가 올라가도 온톨로지 통과가 자동으로 보장되지는 않았다\n\n"
                 "같은 생성 루프를 사용해도 "
                 "원문 필수어, 급수 어휘, 길이와 필수 관계 조건의 조합에 따라 결과가 달라졌다. "
                 "따라서 현재 정책은 생성 후 차단 게이트로는 작동하지만, 모든 급수에서 안정적으로 PASS를 만드는 수준은 아니다."},
        {"id": "ontology-chart", "type": "chart", "chartId": "ontology-by-grade", "layout": "full"},
        {"id": "scope", "type": "markdown", "sourceId": source_id,
         "body": "## 범위와 판정 기준\n\n"
                 "비교 단위는 원문 2개 × 급수 6개다. 지문은 2026년 8월 12일 온톨로지 생성·AI 검증·수정 루프의 최종 결과를 사용했고, "
                 "이번 후속 실험에서 현재 `ontology/policy/validation_policy.json`으로 다시 판정했다. "
                 "각 지문에서는 중심 생각과 내용 일치 문항을 한 개씩 새로 생성했다. 문항 PASS는 질문 존재, 선택지 4개, "
                 "정답의 선택지 포함, 해설 존재를 모두 만족한 경우다."},
        {"id": "method", "type": "markdown", "sourceId": source_id,
         "body": "## 실험 방법\n\n"
                 "1. 저장된 최종 지문과 마지막 어휘 감사를 불러왔다.\n"
                 "2. 길이, 급수 어휘, 원문 필수어, 원문·급수·텍스트 유형 관계를 현재 온톨로지 정책으로 재검증했다.\n"
                 "3. 로컬 `gemma4:12b`에 지문별 대표 읽기 문항 2개를 한 번의 JSON 호출로 생성시켰다.\n"
                 "4. 문항 구조를 결정론적으로 검사하고 원문·판정·문항을 동일 결과 JSON에 저장했다."},
        {"id": "workflow", "type": "markdown",
         "body": "## 온톨로지 기반 평가 생성 워크플로우\n\n"
                 "```text\n"
                 "교수자 자료 입력\n"
                 "      ↓\n"
                 "자료 분석·목표 급수와 유형 설정\n"
                 "      ↓\n"
                 "급수별 지문 생성\n"
                 "      ↓\n"
                 "언어 품질 검증·자연스러움 수정\n"
                 "      ↓ 기준 미충족 시 재생성\n"
                 "읽기 문항 생성\n"
                 "      ↓\n"
                 "온톨로지 구조 진단\n"
                 "      ↓\n"
                 "교수자 검토·승인\n"
                 "      ↓\n"
                 "학습자 제공·채점\n"
                 "```\n\n"
                 "자연스러운 문장 생성과 온톨로지 구조 진단을 분리한다. 온톨로지는 문장을 다시 쓰지 않고 "
                 "지문과 원자료, 목표 급수, 텍스트 유형, 어휘·문법의 연결을 생성 후 확인한다."},
        {"id": "framework", "type": "markdown",
         "body": "## 온톨로지 기반 평가 생성 프레임워크\n\n"
                 "```text\n"
                 "⑤ 활용        교수자 화면 · 학습자 화면 · 평가 결과\n"
                 "────────────────────────────────────────────\n"
                 "④ 생성·검증   지문·문항 생성 · 언어 품질 검증 · 수정 루프\n"
                 "────────────────────────────────────────────\n"
                 "③ 온톨로지    원자료·급수·유형·어휘·문법 관계와 제약\n"
                 "────────────────────────────────────────────\n"
                 "② 평가 기준   성취기준 · 생성 기준 · 문항 유형 · 루브릭\n"
                 "────────────────────────────────────────────\n"
                 "① 근거 자료   교육과정 · TOPIK · SKA · 공공기관 원문\n"
                 "```\n\n"
                 "이 프레임워크는 교육 자료와 평가 기준을 바탕으로 자연스러운 지문을 먼저 만들고, 온톨로지가 "
                 "표현을 강제하지 않은 채 생성 결과의 근거와 관계 구조를 진단하도록 설계한 구조다."},
        {"id": "summary-table-intro", "type": "markdown", "sourceId": source_id,
         "body": "## 12개 조합의 정확한 판정\n\n"
                 "표는 원문·급수별 최종 상태와 실패 규칙을 정확히 조회하기 위한 감사용 결과다.\n\n"
                 + "\n".join(summary_table_md)},
    ]

    for record in records:
        label = SOURCE_LABELS[record["source_key"]]
        failed_items = [x for x in record["ontology_validation"]["items"] if not x["passed"]]
        failed_md = "\n".join(
            f"- **{x['criterion_id']}**: {x['evidence']} — {x['revision_instruction']}"
            for x in failed_items
        ) or "- 실패 규칙 없음"
        questions = []
        for index, item in enumerate(record["reading_items"], 1):
            choices = "\n".join(f"  {n}. {choice}" for n, choice in enumerate(item.get("choices", []), 1))
            questions.append(
                f"### 문항 {index} · {item.get('question_type', '')}\n\n"
                f"**{item.get('question', '')}**\n\n{choices}\n\n"
                f"- 정답: **{item.get('answer', '')}**\n"
                f"- 해설: {item.get('explanation', '')}"
            )
        body = (
            f"## {label} · {record['grade']}급\n\n"
            f"**텍스트 유형:** {record['text_type']}  \n"
            f"**생성·수정 회차:** {record['rounds_used']}회  \n"
            f"**온톨로지:** {'PASS' if record['ontology_validation']['passed'] else '검토 필요'}  \n"
            f"**문항 구조:** {record['question_status'].replace('NEEDS_HUMAN_REVIEW', '검토 필요')}\n\n"
            f"### 최종 지문\n\n{record['generated_passage']}\n\n"
            f"### 온톨로지 실패 근거\n\n{failed_md}\n\n"
            + "\n\n".join(questions)
        )
        blocks.append({
            "id": f"detail-{record['source_key']}-{record['grade']}",
            "type": "markdown", "sourceId": source_id, "body": body,
        })

    blocks.extend([
        {"id": "limitations", "type": "markdown", "sourceId": source_id,
         "body": "## 한계와 견고성 확인\n\n"
                 "이번 결과는 단일 로컬 모델과 저장된 한 번의 생성 이력에 대한 기술적 검증이다. 문항 구조 PASS는 오답의 매력도, "
                 "정답 유일성, 한국어 자연스러움까지 보장하지 않는다. 온톨로지 실패 역시 정책의 엄격함과 사전 등재 범위에 영향을 받는다. "
                 "다만 모든 급수를 같은 원문·정책·형식 검사로 비교했고, 규칙별 근거를 보존했으므로 실패 패턴을 재현하고 수정하기에는 충분하다."},
        {"id": "next-steps", "type": "markdown",
         "body": "## 다음 안정화 작업\n\n"
                 "- 반복 실패가 많은 온톨로지 규칙을 원문·급수별로 분해해 정책 오류와 생성 오류를 구분한다.\n"
                 "- 문항에는 정답 유일성, 지문 근거 문장, 오답 오류 유형 검사를 추가한다.\n"
                 "- 같은 조건을 여러 시드로 반복해 PASS 재현율을 확인한 뒤에만 앱 검증 흐름으로 옮긴다."},
        {"id": "questions", "type": "markdown",
         "body": "## 추가로 확인할 질문\n\n"
                 "온톨로지의 급수 초과어 예외를 어디까지 허용할지, 1·2급 자유 개작에서 원문 필수어 관계를 동일하게 강제할지, "
                 "그리고 문항 의미 검증을 규칙 기반으로 둘지 별도 모델 검증으로 둘지가 다음 의사결정 포인트다."},
    ])

    cards = [
        {"id": "combinations", "description": "두 원문 × 1~6급", "dataset": "metrics", "sourceId": source_id,
         "metrics": [{"label": "지문 조합", "field": "total_combinations", "format": "number"}]},
        {"id": "items", "description": "조합당 대표 문항 2개", "dataset": "metrics", "sourceId": source_id,
         "metrics": [{"label": "생성 문항", "field": "total_items", "format": "number"}]},
        {"id": "ontology-pass", "description": "현재 정책의 모든 Violation 통과", "dataset": "metrics", "sourceId": source_id,
         "metrics": [{"label": "온톨로지 PASS", "field": "ontology_pass", "format": "number"}]},
        {"id": "question-pass", "description": "문항 2개의 필수 구조 통과", "dataset": "metrics", "sourceId": source_id,
         "metrics": [{"label": "문항 구조 PASS", "field": "question_pass", "format": "number"}]},
        {"id": "overall-pass", "description": "온톨로지와 문항 구조 동시 통과", "dataset": "metrics", "sourceId": source_id,
         "metrics": [{"label": "종합 PASS", "field": "overall_pass", "format": "number"}]},
    ]
    chart = {
        "id": "ontology-by-grade", "title": "원문·급수별 온톨로지 통과 여부",
        "subtitle": "1=PASS, 0=검토 필요; 두 원문 각각 1~6급", "type": "bar",
        "dataset": "summary", "sourceId": source_id, "layout": "full",
        "encodings": {
            "x": {"field": "grade", "type": "ordinal", "label": "급수"},
            "y": {"field": "ontology_pass", "type": "quantitative", "label": "통과 여부"},
            "color": {"field": "source", "type": "nominal", "label": "원문"},
            "tooltip": [
                {"field": "source", "type": "text", "label": "원문"},
                {"field": "grade", "type": "ordinal", "label": "급수"},
                {"field": "failed_rules", "type": "text", "label": "실패 규칙"},
            ],
        },
        "surface": {"legend": "visible", "valueLabels": "visible"},
    }
    table = {
        "id": "result-summary", "title": "원문·급수별 자동 검증 결과",
        "subtitle": "총 12개 조합; 실패 규칙은 현재 온톨로지 정책 기준", "dataset": "summary",
        "sourceId": source_id, "density": "spacious", "layout": "full",
        "columns": [
            {"field": "source", "label": "원문", "type": "text"},
            {"field": "grade", "label": "급수", "format": "number"},
            {"field": "text_type", "label": "텍스트 유형", "type": "text"},
            {"field": "rounds", "label": "생성 회차", "format": "number"},
            {"field": "ontology_status", "label": "온톨로지", "type": "text"},
            {"field": "question_status", "label": "문항 구조", "type": "text"},
            {"field": "overall_status", "label": "종합", "type": "text"},
            {"field": "failed_rules", "label": "실패 규칙", "type": "text"},
        ],
    }
    source = {
        "id": source_id,
        "label": "온톨로지 지문·문항 후속 실험 결과",
        "path": "experiments/ontology_passage_question_2026-08-17/report_data.sqlite",
        "query": {
            "engine": "sqlite",
            "sql": query_sql,
            "description": "두 원문 1~6급의 온톨로지·문항 자동 검증 결과",
            "tables_used": ["experiment_summary"],
            "metric_definitions": [
                "ontology_pass=1은 모든 Violation 규칙 통과",
                "문항 구조 PASS는 질문·선택지 4개·선택지 내 정답·해설 존재",
            ],
        },
    }
    artifact = {
        "surface": "report",
        "manifest": {
            "version": 1, "surface": "report",
            "title": "온톨로지 적용 지문·문항 생성 실험",
            "description": "반려동물 동반 음식점과 민간기업 에너지 절약 원문을 1~6급으로 비교",
            "generatedAt": generated_at,
            "charts": [chart], "sources": [source], "blocks": blocks,
        },
        "snapshot": {
            "version": 1, "generatedAt": generated_at, "status": "ready",
            "datasets": {"metrics": metric_rows, "summary": summary_rows},
        },
        "sources": [source],
    }
    output = experiment / "artifact.json"
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    notes = {
        "audience": "technical",
        "chart_map": [{
            "section": "급수가 올라가도 온톨로지 통과가 자동으로 보장되지는 않았다",
            "question": "원문과 급수별 온톨로지 통과 여부는 어떻게 다른가",
            "family": "comparison", "type": "grouped bar",
            "fields": ["grade", "ontology_pass", "source"],
            "claim": "통과 여부는 급수만으로 단조롭게 개선되지 않는다",
            "palette": "categorical with source labels",
        }],
    }
    (experiment / "report_notes.json").write_text(
        json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(output)


if __name__ == "__main__":
    main()
