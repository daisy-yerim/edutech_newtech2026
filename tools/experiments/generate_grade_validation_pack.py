"""1~6급별 지문 3개와 읽기·쓰기 문항을 생성해 전문가 검증 묶음으로 저장한다."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.core.llm import call_gemma_json
from app.services.generation_standards import grade_requirements, standard_prompt

OUT = ROOT / "experiments" / "expert_validation_2026-07"

SOURCES = [
    {
        "id": "S1",
        "title": "성군 세종대왕 탄신 627돌 기념 ‘숭모제전’ 거행",
        "agency": "문화재청(현 국가유산청)",
        "published": "2024-05-13",
        "url": "https://m.korea.kr/news/pressReleaseView.do?newsId=156630194&pWise=mSub&pWiseSub=C8",
        "license": "공공누리 제1유형(출처표시), 텍스트만 이용",
        "facts": [
            "세종대왕 탄신일인 5월 15일에 세종대왕릉에서 숭모제전이 열린다.",
            "행사에는 여민락 연주와 봉래의 공연, 남사당놀이 등이 포함된다.",
            "한글 창제뿐 아니라 과학·예술·국방 등 여러 업적을 되새기는 목적이다.",
            "당일 세종대왕릉과 효종대왕릉을 무료로 개방한다."
        ],
    },
    {
        "id": "S2",
        "title": "행복청, 복합주민공동시설 통합설계로 공동체 문화 확산",
        "agency": "행정중심복합도시건설청",
        "published": "2019-06-19",
        "url": "https://m.korea.kr/briefing/pressReleaseView.do?call_from=rsslink&newsId=156337109",
        "license": "공공누리 제1유형(출처표시), 텍스트만 이용",
        "facts": [
            "행정·복지·체육·문화시설과 학교를 함께 설계해 이용 편의와 예산 절감을 높이려는 계획이다.",
            "학생, 학부모, 주민, 어르신이 같은 공간을 이용하며 공동체 문화를 만들 수 있다.",
            "도서관, 인공암벽장, 달리기 원형주로와 같은 시설을 계획했다.",
            "통합설계는 중복 설계를 줄이고 시설 이용률을 높일 수 있다는 기대를 받는다."
        ],
    },
    {
        "id": "S3",
        "title": "MZ세대와 함께 만드는 폐어구 없는 바다",
        "agency": "해양수산부",
        "published": "2025-05-09",
        "url": "https://m.korea.kr/news/pressReleaseView.do?newsId=156688307&pWise=mSub&pWiseSub=C1",
        "license": "공공누리 제1유형(출처표시), 텍스트만 이용",
        "facts": [
            "대학생, 청년 자문단, 전문가 등 약 250명이 해양환경 포럼에 참여했다.",
            "어구 보증금제, 친환경 어구 보급, 폐어구 재활용 확대를 논의했다.",
            "정부와 청년 세대가 바다 환경 문제 해결을 위해 의견을 나누었다.",
            "열린 정책 소통과 청년의 창의적 관점을 정책에 반영하려는 목적이 있다."
        ],
    },
]

TYPE_ROTATION = [
    ["화제", "내용 일치", "어휘 의미", "순서", "중심 생각", "추론"],
    ["제목", "내용 일치", "원인·결과", "목적", "필자 태도", "정보 통합"],
    ["중심 생각", "세부 정보", "추론", "문단 관계", "근거 평가", "함의"],
]


def prompt_for(grade: int, source_index: int) -> str:
    source = SOURCES[source_index]
    req = grade_requirements(grade)
    types = TYPE_ROTATION[source_index][:req["reading_item_count"]]
    facts = "\n".join(f"- {fact}" for fact in source["facts"])
    return f"""당신은 한국어 평가 도구 개발자입니다. 전문가 내용타당도 검증용 실험 세트 1개를 만드세요.

[중요]
- 아래 사실만 사용하고, 원문의 문장을 복제하지 말고 완전히 새 문장으로 구성하세요.
- 지문에 없는 사실·수치·인과를 만들지 마세요.
- 목표 등급의 길이, 문장 복잡도, 문단 수, 쓰기 분량을 정확히 지키세요.
- 읽기 선택형은 선택지 4개, 정답 1개여야 합니다.
- 해설에는 지문의 근거 문장을 짧게 지시하고 오답 배제 이유를 포함하세요.
- 쓰기는 여러 타당 답안을 허용하며 예시답안을 유일 정답처럼 만들지 마세요.

[목표 등급 읽기 기준]
{standard_prompt(grade, "reading")}

[목표 등급 쓰기 기준]
{standard_prompt(grade, "writing")}

[공개 자료의 사실 요약]
{facts}

[읽기 문항 유형: 순서대로 정확히 {len(types)}개]
{json.dumps(types, ensure_ascii=False)}

다음 JSON 객체 하나만 출력하세요.
{{
  "passage_title": "새 제목",
  "passage": "등급 기준에 맞는 새 지문",
  "reading_items": [
    {{
      "type": "지정 유형",
      "question": "질문",
      "choices": ["① ...", "② ...", "③ ...", "④ ..."],
      "answer": "정답 선택지 전체",
      "explanation": "지문 근거와 오답 배제 이유"
    }}
  ],
  "writing_task": {{
    "genre": "등급 기준에 맞는 장르",
    "instruction": "지문을 활용하는 쓰기 지시문",
    "conditions": ["공백 포함 권장 분량", "필수 내용", "요구 기능"],
    "required_content": ["채점 시 확인할 핵심 내용"],
    "sample_answer": "권장 분량에 맞는 하나의 참고 답안",
    "scoring_notes": "이 등급에서 허용할 오류와 기대할 구조"
  }}
}}"""


def validate_pack(pack: dict, grade: int, source_index: int) -> dict:
    req = grade_requirements(grade)
    passage = pack.get("passage", "")
    items = pack.get("reading_items", [])
    expected_types = TYPE_ROTATION[source_index][:req["reading_item_count"]]
    sample_answer = pack.get("writing_task", {}).get("sample_answer", "")
    checks = {
        "passage_length": req["passage_chars"][0] <= len(passage) <= req["passage_chars"][1],
        "reading_count": len(items) == req["reading_item_count"],
        "reading_types": [item.get("type") for item in items] == expected_types,
        "four_choices_each": all(len(item.get("choices", [])) == 4 for item in items),
        "answer_in_choices": all(item.get("answer") in item.get("choices", []) for item in items),
        "sample_answer_length": req["writing_chars"][0] <= len(sample_answer) <= req["writing_chars"][1],
        "writing_fields": all(pack.get("writing_task", {}).get(key) for key in (
            "genre", "instruction", "conditions", "required_content", "sample_answer", "scoring_notes"
        )),
    }
    return {
        "passed": all(checks.values()), "checks": checks,
        "measured_passage_chars": len(passage),
        "measured_sample_answer_chars": len(sample_answer),
    }


def to_markdown(record: dict) -> str:
    pack, source = record["output"], record["source"]
    lines = [
        f"# {record['grade']}급 실험 {record['experiment_no']}: {pack.get('passage_title', '')}",
        "", "## 실험 메타데이터", "",
        f"- 생성 모델: `{record['model']}`",
        f"- 생성일: {record['generated_at']}",
        f"- 기계 검증: {'통과' if record['mechanical_validation']['passed'] else '재검토 필요'}",
        f"- 원자료: [{source['title']}]({source['url']})",
        f"- 작성 기관/일자: {source['agency']} / {source['published']}",
        f"- 이용 조건: {source['license']}",
        "", "## 읽기 지문", "", pack.get("passage", ""), "", "## 읽기 문항", ""
    ]
    if record.get("assigned_text_type"):
        lines.insert(7, f"- 배정 지문 유형: {record['assigned_text_type']}")
        lines.insert(8, f"- 실제 출력 유형: {pack.get('passage_text_type', '')}")
    if record.get("repair_status"):
        lines.insert(9, f"- 수정 재실험 상태: {record['repair_status']}")
        lines.insert(10, f"- 수정 이력 수: {len(record.get('repair_history', []))}")
    for i, item in enumerate(pack.get("reading_items", []), 1):
        lines.extend([f"### {i}. {item.get('type', '')}", "", item.get("question", "")])
        lines.extend(f"- {choice}" for choice in item.get("choices", []))
        lines.extend(["", f"정답: {item.get('answer', '')}", "", f"해설: {item.get('explanation', '')}", ""])
    task = pack.get("writing_task", {})
    lines.extend(["## 쓰기 문항", "", f"장르: {task.get('genre', '')}", "", task.get("instruction", ""),
                  "", "조건:", ""])
    lines.extend(f"- {value}" for value in task.get("conditions", []))
    lines.extend(["", "필수 내용:", ""])
    lines.extend(f"- {value}" for value in task.get("required_content", []))
    lines.extend(["", "### 예시답안(유일 정답 아님)", "", task.get("sample_answer", ""),
                  "", f"채점 메모: {task.get('scoring_notes', '')}", "",
                  "## 전문가 검증란", "",
                  "- [ ] 등급 적합성", "- [ ] 지문 사실성", "- [ ] 문항 정답 유일성",
                  "- [ ] 쓰기 과제 명료성", "- [ ] 저작권·출처 표시", "- 수정 의견:", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grades", nargs="*", type=int, default=list(range(1, 7)))
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for grade in args.grades:
        grade_dir = OUT / f"grade_{grade}"
        grade_dir.mkdir(exist_ok=True)
        for source_index, source in enumerate(SOURCES):
            json_path = grade_dir / f"experiment_{source_index + 1}.json"
            if json_path.exists():
                continue
            output = call_gemma_json(prompt_for(grade, source_index), temperature=0.35)
            record = {
                "grade": grade, "experiment_no": source_index + 1,
                "model": "gemma4:12b", "generated_at": date.today().isoformat(),
                "source": source, "grade_requirements": grade_requirements(grade),
                "output": output, "mechanical_validation": validate_pack(output, grade, source_index),
                "status": "provisional_pending_expert_review",
            }
            json_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            json_path.with_suffix(".md").write_text(to_markdown(record), encoding="utf-8")
            print(f"{grade}급-{source_index + 1}: {'PASS' if record['mechanical_validation']['passed'] else 'CHECK'}")


if __name__ == "__main__":
    main()
