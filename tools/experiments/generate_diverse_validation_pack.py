"""새 원자료와 다양한 담화 형식으로 두 번째 1~6급 검증 묶음을 생성한다."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.core.llm import call_gemma_json
from app.services.generation_standards import grade_requirements, standard_prompt
from generate_grade_validation_pack import TYPE_ROTATION, to_markdown, validate_pack

OUT = ROOT / "experiments" / "expert_validation_diverse_2026-07"

SOURCES = [
    {
        "id": "N1",
        "title": "오늘부터, 반려동물 동반출입 음식점 반려동물과 함께 이용할 수 있어요",
        "agency": "식품의약품안전처",
        "published": "2026-03-03",
        "url": "https://m.korea.kr/briefing/pressReleaseView.do?newsId=156746806",
        "license": "공공누리 제1유형(출처표시), 텍스트만 이용",
        "facts": [
            "2026년 3월 3일부터 반려동물 동반출입 음식점 제도가 시행되었다.",
            "제도의 목적은 반려동물과 함께 음식점을 이용할 수 있게 하는 것이다.",
            "식품의약품안전처는 제도 정착을 지원하고 현장과 소통하고 있다.",
            "원자료 페이지에는 공공누리 제1유형이 표시되어 있다."
        ],
    },
    {
        "id": "N2",
        "title": "행복도시, 미래형 첨단 스마트 교통도시로 거듭난다",
        "agency": "행정중심복합도시건설청",
        "published": "2017-06-15",
        "url": "https://m.korea.kr/briefing/pressReleaseView.do?newsId=156208378",
        "license": "공공누리 제1유형(출처표시), 텍스트만 이용",
        "facts": [
            "행복도시는 보행, 자전거, 대중교통 중심의 교통 기반을 구축했다.",
            "교통 안전을 높이기 위해 회전교차로를 확대했다.",
            "도심부 제한속도를 시속 60킬로미터에서 50킬로미터로 낮췄다.",
            "교통 흐름과 안전성을 함께 높이는 것이 정책의 목적이다."
        ],
    },
    {
        "id": "N3",
        "title": "우주개발과 우주안보의 시너지 확대를 위한 우주청-국방부 협의회 개최",
        "agency": "우주항공청",
        "published": "2026-01-28",
        "url": "https://m.korea.kr/briefing/pressReleaseView.do?newsId=156741745",
        "license": "공공누리 제1유형(출처표시), 텍스트만 이용",
        "facts": [
            "우주항공청과 국방부가 우주 분야의 민·군 협력을 논의하는 실무협의회를 열었다.",
            "두 기관은 우주발사장 기반시설 구축과 국내 발사체 활용 확대에 협력하기로 했다.",
            "위성정보를 정부 부처와 산업계가 폭넓게 활용하는 방안도 논의했다.",
            "국가 우주산업 발전과 안보 역량을 함께 높이는 것이 협의회의 목표다."
        ],
    },
]

TEXT_TYPES = {
    1: ["생활 공지문", "안전 표지문", "행사 시간표와 짧은 안내"],
    2: ["손님과 직원의 대화", "친구에게 보내는 생활 이메일", "질문·답변형 안내문"],
    3: ["이용 후기", "관계자 짧은 인터뷰", "청소년 신문 기사"],
    4: ["제도 안내 기사", "비교·설명 기사", "전문가 문답 기사"],
    5: ["정책 해설문", "성과 보고서", "쟁점 중심 칼럼"],
    6: ["비판적 사설", "정책 분석 보고서", "복수 관점 논설문"],
}


def prompt_for(grade: int, source_index: int) -> str:
    source = SOURCES[source_index]
    req = grade_requirements(grade)
    text_type = TEXT_TYPES[grade][source_index]
    types = TYPE_ROTATION[(source_index + 1) % len(TYPE_ROTATION)][:req["reading_item_count"]]
    facts = "\n".join(f"- {fact}" for fact in source["facts"])
    target_min = min(req["passage_chars"][1], req["passage_chars"][0] + max(30, int(req["passage_chars"][0] * .15)))
    return f"""당신은 한국어 평가 도구 개발자입니다. 전문가 검증용 실험 세트 1개를 만드세요.

[절대 조건]
- 아래 사실만 사용하고 새로운 사실·인물·조건·효과를 만들지 마세요.
- 원문 문장을 복제하지 말고 새로 쓰세요.
- 지문 형식은 반드시 '{text_type}'입니다. 형식 표지(화자명, 문답, 소제목 등)를 자연스럽게 사용하세요.
- 지문은 공백 포함 {target_min}~{req['passage_chars'][1]}자로 작성하세요.
- 읽기 문항은 지정 순서와 유형을 지키고 선택지 4개, 정답 1개로 만드세요.
- answer는 choices 중 하나를 글자 하나도 바꾸지 말고 그대로 복사하세요.
- 쓰기 예시답안은 공백 포함 {req['writing_chars'][0]}~{req['writing_chars'][1]}자로 작성하세요.

[목표 등급 읽기 기준]
{standard_prompt(grade, "reading")}
[목표 등급 쓰기 기준]
{standard_prompt(grade, "writing")}
[원자료 사실 요약]
{facts}
[읽기 문항 유형]
{json.dumps(types, ensure_ascii=False)}

다음 JSON 객체 하나만 출력하세요.
{{
  "passage_title":"제목",
  "passage_text_type":"{text_type}",
  "passage":"지문",
  "reading_items":[{{
    "type":"지정 유형",
    "question":"질문",
    "choices":["① ...","② ...","③ ...","④ ..."],
    "answer":"choices에서 그대로 복사한 정답",
    "explanation":"지문 근거와 오답 배제 이유"
  }}],
  "writing_task":{{
    "genre":"읽기 지문과 다른 적절한 쓰기 장르",
    "instruction":"지문 정보를 활용하는 쓰기 지시문",
    "conditions":["공백 포함 권장 분량","필수 내용","요구 기능"],
    "required_content":["채점 핵심 요소"],
    "sample_answer":"권장 분량의 참고 답안",
    "scoring_notes":"등급별 허용 오류와 기대 구조"
  }}
}}"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for grade in range(1, 7):
        grade_dir = OUT / f"grade_{grade}"
        grade_dir.mkdir(exist_ok=True)
        for source_index, source in enumerate(SOURCES):
            path = grade_dir / f"experiment_{source_index + 1}.json"
            if path.exists():
                continue
            output = call_gemma_json(prompt_for(grade, source_index), temperature=.35)
            record = {
                "grade": grade, "experiment_no": source_index + 1,
                "model": "gemma4:12b", "generated_at": date.today().isoformat(),
                "source": source, "assigned_text_type": TEXT_TYPES[grade][source_index],
                "grade_requirements": grade_requirements(grade), "output": output,
                "mechanical_validation": validate_pack(output, grade, (source_index + 1) % 3),
                "status": "provisional_pending_expert_review",
            }
            path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            path.with_suffix(".md").write_text(to_markdown(record), encoding="utf-8")
            print(f"{grade}-{source_index + 1}: {'PASS' if record['mechanical_validation']['passed'] else 'CHECK'}", flush=True)


if __name__ == "__main__":
    main()
