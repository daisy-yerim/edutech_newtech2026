# -*- coding: utf-8 -*-
"""
passage_node.py — 지문 생성 노드

업로드 자료의 내용을 바탕으로, 목표 등급 어휘 범위 안에서 읽기 지문을 생성한다.

[기존 generator.py 와의 차이]
generator.py 는 등급·주제만으로 지문을 만든다(업로드 자료 개념 없음).
이 노드는 "교수자가 올린 자료에 근거한 지문"을 만드는 게 목적이라
source_text 를 프롬프트에 함께 넣는다.
어휘 전체를 샘플링 없이 통째로 넣는 정책은 generator.py 와 동일하다.
"""

DemoState = dict
from app.core.llm import call_gemma
from app.services.dictionary import prompt_grammar, prompt_vocabulary
from app.services.generation_standards import grade_requirements, standard_prompt
from app.services.vocabulary_control import (
    polish_beginner_topik_flow,
    polish_passage_naturalness,
    simplify_passage_vocabulary,
)


def _build_prompt(
    state: DemoState,
    vocab_text: str,
    vocab_count: int,
    grammar_text: str,
    grammar_count: int,
) -> str:
    grade = state["grade"]
    passage_min, passage_max = grade_requirements(grade)["passage_chars"]
    reject_note = state.get("reject_note", "")
    source_mode = state.get("source_mode", "source_grounded")
    generation_topic = (
        "TOPIK I 일상생활"
        if source_mode == "beginner_free_adaptation"
        else state["topic"]
    )
    text_type = state.get("text_type", "일반 읽기 지문")
    required_keyword = state.get("required_keyword", "")
    required_keyword_context = state.get("required_keyword_context", "")

    revision_block = ""
    if reject_note:
        revision_block = f"""
[이전 생성에 대한 교수자 수정 요청 — 반드시 반영할 것]
{reject_note}
"""

    ska_block = standard_prompt(grade, "reading")
    material_instruction = (
        "아래 자료의 사실만 사용하여 지문을 작성하세요. 자료의 문장을 그대로 베끼지 마세요."
        if source_mode == "source_grounded"
        else (
            "아래 입력은 1~2급 소재 선택을 위한 느슨한 참고 제목입니다. 원문 본문을 개작하거나 세부 사실을 보존할 필요가 없습니다. "
            "제102회 TOPIK I의 일상적이고 구체적인 짧은 지문처럼 독립적인 상황을 만드세요. "
            "참고 제목의 전문 제도·수치·기관·정책을 넣지 않아도 되며, 더 쉬운 일상 소재로 바꾸어도 됩니다."
            if source_mode == "beginner_free_adaptation"
            else
            (
            "아래 내용은 사실 자료가 아니라 생성 테마입니다. 테마에 맞는 일상적 상황을 새로 구성할 수 있지만, "
            "특정 수치·날짜·법령·기관·정책을 사실처럼 임의로 만들지 마세요."
            )
        )
    )
    beginner_hard_rules = (
        "[TOPIK I 필수 통과 조건]\n"
        + (
            "- 반드시 3~5개의 짧은 문장만 쓰세요.\n"
            "- 1급 어휘 DB에 등록된 1급 이하 어휘만 쓰세요.\n"
            if grade == 1 else
            "- 반드시 4~7개의 짧은 문장만 쓰세요.\n"
            "- 2급 어휘 DB에 등록된 2급 이하 어휘만 쓰세요.\n"
        )
        + "- 원자료 주제보다 TOPIK I의 쉬운 일상 장면을 우선하세요.\n"
        f"- 원자료 핵심어 ‘{required_keyword}’를 지문에 반드시 한 번 이상 쓰세요.\n"
        f"- 핵심어는 반드시 다음 원문 의미로 쓰세요: {required_keyword_context}\n"
        "- 핵심어 외의 급수 초과어는 허용하지 말고, 쉬운 말을 고르는 데 그치지 말고 문장 전체를 자연스럽게 다시 쓰세요.\n"
        "- 설명, 참고, 교정 메모 없이 지문만 출력하세요."
        if source_mode == "beginner_free_adaptation" else ""
    )

    return f"""당신은 한국어 교육 전문가입니다. 외국인 유학생을 위한 한국어 읽기 지문을 만드세요.

[목표 등급]
{grade}급 (국제 통용 한국어 표준 교육과정 기준)

[주제]
{generation_topic}

[필수 텍스트 유형]
{text_type}
- 유형의 목적과 조직이 실제 글에 드러나야 합니다. 제목만 유형처럼 붙이지 마세요.

[SKA 읽기 생성 기준]
{ska_block}

[생성 입력 — 모드: {source_mode}]
{material_instruction}
{beginner_hard_rules}
{grade}급 학습자가 읽을 수 있는 수준으로 쓰세요.
---
{state['source_text']}
---
{revision_block}
[관련 권장 어휘]
등급별 사전에서 참고 자료와 관련된 {grade}급 이하 어휘 {vocab_count}개를 조회했습니다.
자연스러운 범위에서 이 어휘를 우선 사용하세요. 목록은 전체 허용 어휘가 아니므로
필요하면 다른 {grade}급 이하 기본 어휘와 고유명사도 사용할 수 있습니다.
권장 어휘: {vocab_text}

[반복·자연스러움 통제]
- 핵심 주제어는 이해에 필요한 만큼 반복할 수 있지만, 같은 내용어·연결어·종결형을 가까운 문장에서 불필요하게 반복하지 마세요.
- 반복을 피하려고 목표 등급보다 어려운 동의어나 한자어를 새로 넣지 마세요. 쉬운 대용 표현이나 문장 결합·분리를 사용하세요.
- 1~2급은 쉬운 어휘를 안정적으로 반복하는 것을 어휘 다양성보다 우선하되, 모든 문장을 같은 종결형과 같은 구조로 만들지 마세요.
- 3~6급은 목표 등급 범위 안에서 내용어·연결 표현과 문장 구조를 점진적으로 다양화하세요.
- 생성 후 각 문장의 주어와 서술어, 수식 관계, 지시 대상, 앞뒤 인과·시간 관계를 스스로 확인하세요.
- 문법적으로 가능해도 실제 한국어에서 뜻이 통하지 않거나 앞뒤 문맥과 맞지 않는 문장은 다시 쓰세요.
- 뜻을 짐작할 수 있다는 이유만으로 어색한 결합·연결·시간 표현을 허용하지 마세요. 실제 한국어 화자가 자연스럽게 쓰는 문장으로 고치세요.

[문맥 연결 필수 설계]
- 쓰기 전에 내부적으로 `중심 대상 → 사건/정보의 순서 → 마지막 문장의 역할`을 정한 뒤, 그 계획에 필요한 문장만 쓰세요. 계획은 출력하지 마세요.
- 새 문장은 앞 문장의 사람·대상·장소·시간·원인 중 적어도 하나를 이어 받아야 합니다. 아무 연결 없이 새 인물이나 새 상황을 시작하지 마세요.
- 같은 사람이나 대상을 가리키는 이름·대명사·생략 주어를 일관되게 사용하고, `이것·그곳·그 일`의 대상이 바로 앞 문맥에서 하나로 정해지게 하세요.
- 시간 순서나 원인·결과가 바뀌면 해당 급수에서 허용되는 연결 표현으로 관계를 명시하세요.
- 1~2급은 한 장면 안에서 1급은 `상황→행동→결과`, 2급은 `상황→행동→이유/결과`의 선형 흐름을 우선하세요. 서로 관련 없는 쉬운 문장을 나열하면 안 됩니다.

[TOPIK형 정보 전개]
- 원자료의 사실을 모두 나열하지 말고, 선택한 읽기 유형으로 평가할 수 있는 하나의 중심 정보 흐름만 고르세요.
- 연결어를 많이 넣는 것이 자연스러움은 아닙니다. 앞 문장의 핵심 명사·행동·상황을 다음 문장이 구체화하거나 그 이유·결과를 설명하게 하세요.
- 같은 뜻의 권유·평가·결론을 표현만 바꾸어 반복하지 마세요. 마지막 문장은 새 주제를 시작하지 말고 앞 내용을 마무리해야 합니다.
- 1급: 한 장소와 한 상황에서 `상황→행동→결과`를 정확히 3~5문장으로 전개하세요.
- 2급: 한 상황에서 `상황→행동→간단한 이유 또는 결과`를 정확히 4~7문장으로 전개하세요.
- 1~2급에서는 핵심 행동과 관계없는 식사 약속·감정·응원·추가 계획을 넣지 마세요. 모든 문장이 같은 사람·장소·목적을 이어 가야 합니다.
- 3~4급: 첫 문장에서 중심 정보를 제시하고, 이어지는 문장은 관련 사실을 두 묶음 이하로 설명한 뒤 결과나 계획으로 마무리하세요.
- 5~6급: `배경·핵심 내용→구체적 근거·방법→의미·전망`의 문단 역할을 구분하세요. 한 문단에 서로 다른 세부 규칙을 무리하게 몰아넣지 마세요.
- 3급은 전문 용어를 무조건 일상어로 바꾸지 마세요. 필요한 용어는 유지하고 바로 다음 문장에서 정확한 의미를 자연스럽게 설명하세요. `규칙이 시작된다`, `움직임을 막는다`처럼 뜻은 짐작되지만 실제 안내문에서 어색한 표현은 쓰지 마세요.
- 4급은 제도명·비율·운영 조건을 괄호 속 즉석 정의로 풀지 마세요. 특히 승용차 5부제 같은 제도명을 임의의 횟수나 카풀 규칙으로 바꾸지 말고 원문의 명칭과 의미를 유지하세요.
- 5급은 세부 방법을 단순 열거하지 말고 `주체의 목표→실행 방법→지원·점검`처럼 관계가 가까운 정보끼리 문단을 구성하세요.
- 6급은 중요한 적용 조건·예외·제한을 관련 규칙 바로 뒤에 배치하세요. 마지막 문장에 예방접종 조건이나 적용 대상을 처음 제시하지 말고, 마지막 문단은 앞서 설명한 정책의 점검·전망으로 마무리하세요.
- 원문에 없는 인과, 정의, 적용 대상, 횟수, 비율을 추론해서 넣지 마세요. 정확히 알 수 없는 개념은 임의로 쉽게 풀지 말고 원문 표현을 유지하세요.
- 원문에 같은 수치나 비슷한 수치가 여러 번 나와도 주체와 행동이 다르면 합치지 마세요. 예를 들어 `승용차 5부제 참여 주체 50여 개`와 `석유 절감 계획 제출 기업 50개사`는 서로 다른 사실로 유지하세요.
- 공지·기사·설명문은 실제 교육용 읽기 자료처럼 중립적이고 간결하게 쓰고, 근거 없는 감정 표현이나 홍보 문구를 덧붙이지 마세요.
- 쉬운 단어를 조합했다는 이유만으로 `시설 설치 돈`처럼 실제 한국어에서 쓰지 않는 결합을 만들지 마세요. 어려운 개념은 자연스러운 기본 표현으로 문장 전체를 다시 구성하세요.

[TOPIK 기출형 문장 경제성]
- 문장마다 주된 정보 관계를 하나만 맡기세요. 한 문장에 배경·목적·방법·평가를 모두 겹쳐 넣지 마세요.
- `최근`, `특히`, `이러한`, `적극적으로`, `다양한`, `주목받고 있다`, `노력하고 있다`, `기여할 것으로 보인다`는 원문에서 대비·범위·태도를 구별하는 정보가 있을 때만 쓰세요.
- 해당 표현을 삭제해도 누가 무엇을 왜·어떻게 하는지가 그대로라면 삭제하세요. 분량을 채우기 위한 평가, 전망, 당위 문장을 만들지 마세요.
- 앞 문장을 추상적으로 되받는 문장보다, 앞 문장의 핵심 명사를 그대로 이어 받아 구체적인 사실을 제시하세요.
- 접속부사는 문단마다 습관적으로 붙이지 말고 의미 관계가 없으면 두 문장을 바로 이어 쓰세요.
- 나열 항목은 문항의 정답 근거가 되는 것만 남기고, 세 항목을 넘으면 성격이 같은 것끼리 묶거나 대표 예만 제시하세요.
- 초안에서 각 문장의 수식어와 평가 표현을 지워 본 뒤 사실 관계가 달라지지 않는 표현은 최종문에서 제외하세요.

[수식어 정책]
- 1~2급: 목표 급수 이하 어휘 DB에 등록된 관형어·형용사·부사는 모두 허용합니다. 수식어라는 이유만으로 삭제하거나 실패 처리하지 마세요.
- 3~6급: 핵심 정보를 구별하거나 관계를 분명하게 하는 수식어는 유지하되, 정보 없이 분위기만 꾸미는 평가·감정 표현과 같은 꾸밈말의 반복은 줄이세요.
- 어느 급수에서도 어려운 명사를 피하려고 뜻이 모호한 수식어구로 우회하지 마세요.

[등급별 권장 문법]
사전에서 조회한 {grade}급 이하 문법 {grammar_count}개를 자연스럽게 활용하세요.
모든 문법을 억지로 사용할 필요는 없습니다.
권장 문법: {grammar_text}

[요청 사항]
위 자료의 핵심 내용을 담은 {grade}급 수준의 읽기 지문을 작성하세요.
- 공백 포함 {passage_min}~{passage_max}자를 목표로 하세요. 핵심 의미의 완결성을 해치지 않는 범위에서 이 길이를 지키고, 분량을 채우기 위한 곁가지 정보는 넣지 마세요.
- 급수는 1급이 가장 쉬운 초급이고 6급이 가장 어려운 고급입니다. 이 순서를 반대로 해석하지 마세요.
- 원자료의 정확한 제도·안전 개념을 쉬운 말로 바꾸다가 의미를 흐리지 마세요. 꼭 필요한 핵심 용어는 유지하고 쉬운 설명을 붙이세요.
- 작성 후 원문의 기관·날짜·수치·대상·의무·금지·지원 관계를 지문과 하나씩 대조하고, 관계의 방향이나 조건이 달라진 문장은 출력 전에 고치세요.
- 원문에 직접 제시되지 않은 `기후 위기 대응`, `탄소 배출 감소` 같은 상위 목적을 상식으로 보충하지 마세요.
지문만 출력하고, 제목이나 설명은 붙이지 마세요.
"""


def passage_node(state: DemoState) -> dict:
    """
    입력: source_text, grade, topic, (reject_note)
    출력: passage
    """
    lookup_context = "\n".join([
        state.get("topic", ""),
        state.get("source_text", ""),
        state.get("reject_note", ""),
    ])
    vocab_text, vocab_count = prompt_vocabulary(lookup_context, state["grade"])
    grammar_text, grammar_count = prompt_grammar("paragraph", state["grade"])
    prompt = _build_prompt(
        state, vocab_text, vocab_count, grammar_text, grammar_count
    )

    passage = call_gemma(prompt).strip()
    requirements = grade_requirements(state["grade"])
    exempt_words = set(state.get("source_terms", []))
    vocabulary_rounds = (
        3 if state["grade"] in {1, 2}
        else 2 if state["grade"] in {3, 4, 5}
        else 0
    )
    passage, vocabulary_audit, vocabulary_revision_history = simplify_passage_vocabulary(
        passage=passage,
        target_grade=state["grade"],
        source_text=state["source_text"],
        min_chars=requirements["passage_chars"][0],
        max_chars=requirements["passage_chars"][1],
        max_rounds=vocabulary_rounds,
        exempt_words=exempt_words,
    )
    passage, vocabulary_audit, beginner_flow_revision = polish_beginner_topik_flow(
        passage=passage,
        target_grade=state["grade"],
        source_text=state["source_text"],
        min_chars=requirements["passage_chars"][0],
        max_chars=requirements["passage_chars"][1],
        exempt_words=exempt_words,
    )
    # Check naturalness after the final beginner restructuring as well.
    passage, vocabulary_audit, naturalness_revision = polish_passage_naturalness(
        passage=passage,
        target_grade=state["grade"],
        source_text=state["source_text"],
        min_chars=requirements["passage_chars"][0],
        max_chars=requirements["passage_chars"][1],
        exempt_words=exempt_words,
    )

    return {
        "passage": passage,
        "vocabulary_audit": vocabulary_audit,
        "vocabulary_revision_history": vocabulary_revision_history,
        "naturalness_revision": naturalness_revision,
        "beginner_flow_revision": beginner_flow_revision,
        "log": [
            f"[지문 생성] {len(passage)}자 (어휘 {vocab_count}개 제약 적용, "
            f"등급 초과 어휘 {vocabulary_audit['violation_count']}개, "
            f"어휘 교체 {len(vocabulary_revision_history)}회, "
            f"자연스러움 교정 {'채택' if naturalness_revision.get('accepted') else '미채택'}, "
            f"라운드 {state.get('round_no', 1)})"
        ],
    }
