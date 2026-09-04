"""Nodes used only by the teacher generation graph."""

from __future__ import annotations

import json

from langgraph.types import interrupt

from app.core.llm import call_gemma_json
from app.services.category_profiles import category_profile, sentence_type_profile
from app.services.generation_standards import grade_requirements, standard_prompt
from app.services.language_control import adjust_language_document
from app.services.rubrics import learner_rubric_for
from app.services.task_repository import publish_assessment
from app.services.teacher_rubrics import rubric_prompt, rubric_section
from app.workflow.nodes.ingest_node import ingest_node
from app.workflow.nodes.passage_node import passage_node
from app.workflow.nodes.reading_node import reading_node

SENTENCE_TYPES = ["writing"]


def _dict_items(value) -> list[dict]:
    """모델이 목록에 문자열을 섞어 반환해도 객체 항목만 사용한다."""
    if isinstance(value, dict):
        return [value]
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def generate_passage(state: dict) -> dict:
    category_topic = (
        f"{state.get('topic', '')}\n"
        f"분류 카테고리: {state.get('category_label', state['category_id'])}"
    )
    targets = state.get("passage_regeneration_targets", [])
    generation_note = "\n".join(
        f"- {item['id']}: {item['instruction']}"
        for item in rubric_section("generation", "passage")
    )
    correction_note = "\n".join(
        f"- {item.get('criterion_id')}: {item.get('revision_instruction', '')}"
        for item in _dict_items(state.get("passage_validation", {}).get("items", []))
        if item.get("criterion_id") in targets
    )
    result = passage_node({
        **state, "topic": category_topic,
        "reject_note": "\n".join(filter(None, [
            state.get("reject_note", ""),
            "[생성 루브릭]", generation_note,
            "[선택된 실패 항목 수정]" if correction_note else "", correction_note,
        ])),
        "round_no": state.get("passage_round", 1),
    })
    return result


def validate_passage(state: dict) -> dict:
    grade_standard = standard_prompt(state["grade"], "reading")
    source_mode = state.get("source_mode", "source_grounded")
    evidence_rule = (
        "P-VAL-01과 P-VAL-02는 원천 자료와의 사실 일치 및 근거 없는 추가 여부를 판정하십시오."
        if source_mode == "source_grounded"
        else (
            "1~2급 자유 개작 모드입니다. 원문 본문과의 사실 일치, 정보 누락, 주제 변경을 실패로 판정하지 마십시오. "
            "P-VAL-01은 독립된 일상 지문으로서 내용이 일관되는지만 보고, P-VAL-02는 실제 기관·법령·정책·수치를 "
            "근거 없이 사실처럼 단정한 경우에만 실패 처리하십시오."
            if source_mode == "beginner_free_adaptation"
            else
            (
            "이 입력은 테마만 제공합니다. P-VAL-01은 지문이 테마에 부합하는지 판정하고, "
            "P-VAL-02는 특정 수치·날짜·법령·기관·정책처럼 검증이 필요한 사실을 근거 없이 단정했는지만 판정하십시오. "
            "일상적인 인물·장소·행동을 새로 구성한 것 자체를 실패로 판정하지 마십시오."
            )
        )
    )
    prompt = f"""당신은 한국어 평가 지문의 독립 검증기입니다. 생성자의 의도를 추측하지 말고
원천 자료와 검증 루브릭을 기준으로 지문을 항목별 판정하세요.

[입력 근거 모드: {source_mode}]
{evidence_rule}

[급수 방향 — 절대 규칙]
- 이 프로젝트에서 1급은 가장 쉬운 초급이고 6급은 가장 어려운 고급입니다.
- 낮은 숫자 급수에 전문 용어, 복잡한 문장, 높은 개념 밀도를 요구하면 안 됩니다.
- P-VAL-03은 아래의 해당 급수 기준만 사용하십시오. 급수에 대한 일반 상식이나 반대 순서를 적용하지 마십시오.

[해당 급수의 확정 생성 기준]
{grade_standard}

[수식어 판정 예외]
- 1~2급에서 목표 급수 이하 어휘 DB에 등록된 관형어·형용사·부사는 모두 허용합니다. 수식어 사용 자체를 실패 근거로 삼지 마십시오.
- 3~6급에서는 핵심 정보와 관계 설명에 필요하지 않은 평가·감정 표현 또는 같은 꾸밈말의 반복만 P-VAL-09에서 실패 처리하십시오.
- 모든 급수에서 어려운 명사를 피하기 위한 뜻이 모호한 수식어구는 자연스러움과 의미 정확성 측면에서 검사하십시오.

[길이 판정]
- 제시된 글자 수는 기출 기반으로 조정한 목표 범위입니다. 약간의 이탈만으로 실패시키지 말되, 3~6급에서 상한을 10% 넘고 중복·곁가지 정보가 있으면 P-VAL-03을 실패 처리하십시오.
- 짧아서 필수 구조나 평가 단서가 사라진 경우에도 P-VAL-03 또는 P-VAL-05를 실패 처리하십시오.

[원천 자료]
{state['source_text']}
[생성 지문]
{state['passage']}
[필수 텍스트 유형]
{state.get('text_type', '일반 읽기 지문')}
- P-VAL-03에서 지문이 지정 유형의 목적과 조직을 실제로 갖추었는지도 판정하십시오.
[1~2급 원문 핵심어 의미]
- 핵심어: {state.get('required_keyword', '해당 없음')}
- 반드시 유지할 원문 의미: {state.get('required_keyword_context', '해당 없음')}
- 핵심어 문자열만 들어 있고 위 의미와 다르게 사용되면 P-VAL-01 또는 P-VAL-03을 실패 처리하십시오.
[자연스러움 강화 판정]
- 뜻을 짐작할 수 있어도 실제 한국어에서 잘 쓰지 않는 결합, 연결, 시간 표현이면 실패입니다.
- 문법 형태가 가능하다는 이유만으로 어색한 문장을 통과시키지 마십시오.
- P-VAL-04에서는 각 문장이 앞 문장의 사람·대상·장소·시간·원인 중 무엇을 이어 받는지 순서대로 확인하십시오. 연결 근거 없이 새 장면이 시작되거나 동일 대상의 명칭·주어가 이유 없이 바뀌면 실패입니다.
- 특히 1~2급은 쉬운 문장 각각이 성립하는지만 보지 말고, 전체가 하나의 장면에서 상황→행동→결과(2급은 이유도 허용)로 이어지는지 검사하십시오.
- 3급은 전문 용어를 부자연스러운 쉬운말로 치환했는지, 4급은 제도명·횟수·수치를 원문에 없는 괄호 풀이로 왜곡했는지 검사하십시오.
- 5급은 목표·방법·지원·점검이 관계별로 묶였는지, 6급은 핵심 적용 조건이나 예외가 마지막에 뒤늦게 추가되지 않았는지 검사하십시오.
- 원문과 지문의 기관·날짜·수치·적용 대상·의무·금지·지원 관계를 하나씩 대조하십시오. 표현이 유창해도 관계 방향이나 조건이 달라지면 P-VAL-01 또는 P-VAL-11을 실패 처리하십시오.
- 같은 수치 또는 비슷한 수치에 연결된 주체와 행동이 서로 다른데 하나의 사실로 합쳐졌는지 검사하십시오. 원문에 없는 기후·탄소 효과를 상식으로 추가한 경우에도 실패 처리하십시오.
- 실제 TOPIK 읽기 지문과 달리 한 문장에 배경·목적·방법·평가가 과도하게 겹쳤는지 검사하십시오. 문장마다 주된 정보 관계가 하나씩 드러나야 합니다.
- `최근`, `특히`, `이러한`, `적극적으로`, `다양한`, `주목받고 있다`, `노력하고 있다`, `사회 전반`, `자리 잡다`, `기여할 것으로 보인다`가 범위·대조·사실 관계를 구별하지 않고 분위기만 꾸미면 P-VAL-09를 실패 처리하십시오.
- 앞 문장을 추상적인 지시어로 되받았지만 지시 대상이 모호하거나 새 정보와의 관계가 약한 경우, 또는 접속부사가 실제 의미 관계 없이 붙은 경우 P-VAL-04나 P-VAL-08을 실패 처리하십시오.
[등급/카테고리]
{state['grade']}급 / {state.get('category_label', state['category_id'])}
[검증 루브릭]
{rubric_prompt('validation', 'passage')}

모든 기준에 대해 다음 JSON만 출력하세요:
{{"items":[{{"criterion_id":"P-VAL-01","passed":true,"evidence":"판정 근거","revision_instruction":"실패 시 구체적 수정 지시"}}]}}"""
    data = call_gemma_json(prompt)
    items = _dict_items(data.get("items", []))
    if not items:
        items = [{
            "criterion_id": "P-VAL-FORMAT", "passed": False,
            "evidence": "검증 응답 형식이 올바르지 않습니다.",
            "revision_instruction": "지문을 다시 검증하세요.",
        }]
    failed = [item["criterion_id"] for item in items if not item.get("passed")]
    # The local validator sometimes approves generic promotional conclusions even
    # when the prompt explicitly asks for a compact TOPIK-style information flow.
    # Make those observable phrases a deterministic repair signal. This does not
    # reject ordinary modifiers; it targets phrases that add no testable fact.
    economy_phrases = [
        "주목받고 있다", "적극적으로 참여", "이러한 노력", "이 같은 노력",
        "노력할 계획", "사회 전반", "자리 잡도록", "실질적인 변화를 이끌",
        "확산될 수 있도록 노력", "기여할 것으로 기대",
    ]
    economy_hits = [phrase for phrase in economy_phrases if phrase in state["passage"]]
    economy_passed = not economy_hits
    items.append({
        "criterion_id": "P-VAL-TOPIK-ECONOMY",
        "passed": economy_passed,
        "evidence": (
            "정보 없는 홍보·평가성 상투 표현 없음"
            if economy_passed else "삭제 검토 표현: " + ", ".join(economy_hits)
        ),
        "revision_instruction": (
            "표시된 평가·홍보 표현을 삭제하고, 그 자리에 원자료의 구체적인 "
            "주체·행동·조건·결과가 있을 때만 사실 문장을 남기세요. "
            "분량을 맞추기 위한 일반 전망은 추가하지 마세요."
        ),
    })
    if not economy_passed:
        failed.append("P-VAL-TOPIK-ECONOMY")
    vocabulary_audit = state.get("vocabulary_audit", {})
    blocked_unknown = vocabulary_audit.get("blocked_unknown_tokens", [])
    required_keyword = state.get("required_keyword", "")
    if state["grade"] in {1, 2} and required_keyword:
        keyword_passed = required_keyword in state["passage"]
        items.append({
            "criterion_id": "P-VAL-SOURCE-KEYWORD",
            "passed": keyword_passed,
            "evidence": (
                f"필수 원문 핵심어 ‘{required_keyword}’ 포함"
                if keyword_passed else f"필수 원문 핵심어 ‘{required_keyword}’ 누락"
            ),
            "revision_instruction": (
                f"원문의 급수 적합 핵심어 ‘{required_keyword}’를 한 번 이상 포함하되 "
                "다른 초과어를 추가하지 말고 문장 전체를 자연스럽게 다시 쓰세요."
            ),
        })
        if not keyword_passed:
            failed.append("P-VAL-SOURCE-KEYWORD")
    if vocabulary_audit.get("violation_count", 0) or blocked_unknown:
        known_evidence = [
            f"{item['word']}({item['grade']}급)"
            for item in vocabulary_audit.get("violations", [])
        ]
        unknown_evidence = [
            f"{item['word']}(미등록 내용어)" for item in blocked_unknown
        ]
        beginner_vocab_failed = state["grade"] <= 5
        vocabulary_criterion = (
            "P-VAL-VOCAB" if beginner_vocab_failed else "P-VAL-VOCAB-ADVISORY"
        )
        items.append({
            "criterion_id": vocabulary_criterion,
            "passed": not beginner_vocab_failed,
            "evidence": "등급 검토 참고 어휘: " + ", ".join(
                known_evidence + unknown_evidence
            ),
            "revision_instruction": (
                "표시된 어휘를 목표 등급 이하의 등록 어휘로 교체하세요. "
                "단, 원문의 정확한 핵심 개념은 모호하게 바꾸지 말고 짧은 쉬운 설명을 덧붙이세요."
            ),
        })
        # 1~5급은 실제 목표 급수 초과어를 수정 루프로 돌린다. 6급은
        # 상위 급수가 없으므로 미등록 전문어만 교사 참고로 남긴다.
        if beginner_vocab_failed:
            failed.append(vocabulary_criterion)
    if state["grade"] in {1, 2}:
        import re
        sentence_count = len([
            part for part in re.split(r"[.!?]+", state["passage"]) if part.strip()
        ])
        minimum, maximum = ((3, 5) if state["grade"] == 1 else (4, 7))
        structure_passed = minimum <= sentence_count <= maximum
        items.append({
            "criterion_id": "P-VAL-TOPIK-I-STRUCTURE",
            "passed": structure_passed,
            "evidence": f"문장 수 {sentence_count}개(허용 {minimum}~{maximum}개)",
            "revision_instruction": (
                f"TOPIK I {state['grade']}급 수준으로 {minimum}~{maximum}개의 "
                "짧고 직접적인 문장으로 고치세요."
            ),
        })
        if not structure_passed:
            failed.append("P-VAL-TOPIK-I-STRUCTURE")
    return {
        "passage_validation": {"passed": not failed, "failed_ids": failed, "items": items},
        "log": [f"[지문 AI 검증] 실패 {len(failed)}개"],
    }


def passage_review(state: dict) -> dict:
    payload = interrupt({
        "stage": "passage_review",
        "passage": state.get("passage", ""),
        "grade": state["grade"],
        "topic": state.get("topic", ""),
        "category_id": state["category_id"],
        "category_label": state.get("category_label", state["category_id"]),
        "round_no": state.get("passage_round", 1),
        "generation_rubric": rubric_section("generation", "passage"),
        "validation_rubric": rubric_section("validation", "passage"),
        "validation": state.get("passage_validation", {}),
        "vocabulary_audit": state.get("vocabulary_audit", {}),
        "vocabulary_revision_history": state.get("vocabulary_revision_history", []),
        "approval_rubric": rubric_section("approval", "passage"),
    })
    return {
        "passage_decision": payload.get("decision", "reject"),
        "reject_note": "" if payload.get("decision") == "approve" else payload.get("note", ""),
        "reading_question_types": payload.get("reading_question_types", []),
        "writing_sentence_type": "writing",
        "passage_regeneration_targets": payload.get("regeneration_targets", []),
        "passage_approval_review": payload.get("approval_review", {}),
        "review_history": state.get("review_history", []) + [{
            "stage": "passage", "decision": payload.get("decision", "reject"),
            "reasons": payload.get("approval_review", {}),
        }],
        "log": [f"[지문 검토] {payload.get('decision', 'reject')}"],
    }


def bump_passage(state: dict) -> dict:
    return {"passage_round": state.get("passage_round", 1) + 1}


def generate_reading(state: dict) -> dict:
    rejected_indexes = state.get("reading_regeneration_indexes", [])
    if rejected_indexes and state.get("reading_items"):
        selected = state.get("reading_question_types", [])
        rejected_types = [selected[index] for index in rejected_indexes if index < len(selected)]
        regenerated = reading_node({
            **state,
            "reading_question_types": rejected_types,
            "reject_note": state.get("reject_note", ""),
            "round_no": state.get("assessment_round", 1),
        }).get("reading_items", [])
        merged = list(state["reading_items"])
        for index, item in zip(rejected_indexes, regenerated):
            if index < len(merged):
                merged[index] = item
        merged, language_audit, language_revision_history = adjust_language_document(
            document=merged,
            target_grade=state["grade"],
            task_type="paragraph",
            document_kind="읽기 문항",
            source_text=state.get("source_text", ""),
        )
        return {
            "reading_items": merged,
            "reading_language_audit": language_audit,
            "reading_language_revision_history": language_revision_history,
            "reading_regeneration_indexes": [],
            "log": [f"[문항별 재생성] 읽기 {len(regenerated)}개 교체"],
        }
    if state.get("writing_regeneration") and state.get("reading_items"):
        return {"log": ["[문항별 재생성] 읽기 문항 유지"]}
    targets = state.get("assessment_regeneration_targets", [])
    writing_only = bool(targets) and set(targets) <= {"A-VAL-05"}
    if writing_only and state.get("reading_items"):
        return {"log": ["[선택적 재생성] 읽기 문항 유지"]}
    note = "\n".join(f"- {item['id']}: {item['instruction']}" for item in rubric_section("generation", "assessment"))
    correction_note = "\n".join(
        f"- {item.get('criterion_id')}: {item.get('revision_instruction', '')}"
        for item in _dict_items(state.get("validation", {}).get("items", []))
        if item.get("criterion_id") in targets
    )
    return reading_node({
        **state,
        "reject_note": "\n".join(filter(None, [
            state.get("reject_note", ""), "[생성 루브릭]", note,
            "[선택된 실패 항목 수정]" if correction_note else "", correction_note,
        ])),
        "round_no": state.get("assessment_round", 1),
    })


def _writing_prompt(state: dict) -> str:
    sentence_type = state["writing_sentence_type"]
    profile = sentence_type_profile(state["category_id"], sentence_type)
    rubric = learner_rubric_for(sentence_type, state["grade"])
    targets = state.get("assessment_regeneration_targets", [])
    targeted_corrections = "\n".join(
        f"- {item.get('criterion_id')}: {item.get('revision_instruction', '')}"
        for item in _dict_items(state.get("validation", {}).get("items", []))
        if item.get("criterion_id") in targets
    )
    return f"""당신은 한국어 쓰기 평가 문항 개발자입니다.

[등급 기준]
{standard_prompt(state['grade'], 'writing')}

[선택 조건]
- 등급: {state['grade']}급
- 카테고리: {state.get('category_label', state['category_id'])}
- 문장 유형: {sentence_type}

[승인된 지문]
{state['passage']}

[카테고리·문장유형 데이터 프로필]
{json.dumps(profile, ensure_ascii=False)}

[학습자 채점 기준: 내용·과제 수행 30 + 글의 전개 구조 30 + 언어 사용 40]
{json.dumps(rubric, ensure_ascii=False)}

[교수자 재생성 요청]
{state.get('reject_note', '') or '없음'}
{targeted_corrections}

[문제 생성 루브릭]
{rubric_prompt('generation', 'assessment')}

지문을 근거로 {sentence_type} 쓰기 문제 1개를 만드세요. 예시답안은 유일한 정답이 아니라
필수 내용과 가능한 전개를 보여 주는 참고자료입니다. 다양한 타당 답안을 허용하고 지문에 없는 사실을 단정하지 마세요.
등급 기준에 제시된 답안 길이를 conditions에 반드시 명시하고, 해당 등급의 장르·구조·채점 기대를 반영하세요.
다음 JSON만 출력하세요:
{{
  "instruction": "문제 지시문",
  "conditions": ["작성 조건"],
  "sample_answer": "교수자가 승인할 예시 답안",
  "explanation": "답안 구성과 근거 해설",
  "required_content": ["내용·과제 수행 영역에서 확인할 핵심 내용 요소"],
  "target_vocabulary": ["권장 어휘"],
  "target_grammar": ["권장 문법"],
  "scoring_guide": {{
    "content_task": ["내용·과제 수행 30점에서 확인할 문항별 근거"],
    "organization": ["전개 구조 30점에서 확인할 문항별 수행"],
    "language_use": ["언어 사용 40점에서 확인할 등급별 기대"],
    "cross_domain_note": "내용 오류와 문법 오류를 독립 판정하기 위한 주의점"
  }}
}}"""


def generate_writing(state: dict) -> dict:
    if state.get("writing_task") and not state.get("writing_regeneration"):
        return {"log": ["[문항별 재생성] 쓰기 문항 유지"]}
    targets = state.get("assessment_regeneration_targets", [])
    reading_only = bool(targets) and set(targets) <= {"A-VAL-03", "A-VAL-04"}
    if reading_only and state.get("writing_task"):
        return {"log": ["[선택적 재생성] 쓰기 문항 유지"]}
    task = call_gemma_json(_writing_prompt(state))
    task, language_audit, language_revision_history = adjust_language_document(
        document=task,
        target_grade=state["grade"],
        task_type="essay",
        document_kind="쓰기 과제",
        source_text=state.get("source_text", ""),
    )
    return {
        "writing_task": task,
        "writing_language_audit": language_audit,
        "writing_language_revision_history": language_revision_history,
        "writing_regeneration": False,
        "log": [f"[쓰기 생성] {state['category_id']} / {state['writing_sentence_type']}"],
    }


def validate_assessment(state: dict) -> dict:
    notes = []
    selected = state.get("reading_question_types", [])
    items = _dict_items(state.get("reading_items", []))
    if len(items) != len(selected):
        notes.append("선택한 읽기 유형 수와 생성 문항 수가 다릅니다.")
    for index, item in enumerate(items, 1):
        choices = item.get("choices", [])
        if len(choices) != 4:
            notes.append(f"읽기 {index}번 선택지가 4개가 아닙니다.")
        if item.get("answer") not in choices:
            notes.append(f"읽기 {index}번 정답이 선택지와 일치하지 않습니다.")
        if not item.get("explanation"):
            notes.append(f"읽기 {index}번 해설이 없습니다.")
    required = ["instruction", "sample_answer", "explanation", "required_content", "scoring_guide"]
    missing = [key for key in required if not state.get("writing_task", {}).get(key)]
    if missing:
        notes.append("쓰기 문항 필수 항목 누락: " + ", ".join(missing))
    for label, audit in (
        ("읽기", state.get("reading_language_audit", {})),
        ("쓰기", state.get("writing_language_audit", {})),
    ):
        count = audit.get("vocabulary", {}).get("violation_count", 0)
        if count:
            notes.append(f"{label} 생성물에 목표 등급 초과 어휘가 {count}건 남아 있습니다.")
    prompt = f"""당신은 한국어 읽기·쓰기 평가 문항의 독립 검증기입니다.
[승인 지문] {state['passage']}
[읽기 문항] {json.dumps(items, ensure_ascii=False)}
[쓰기 문항] {json.dumps(state.get('writing_task', {}), ensure_ascii=False)}
[검증 루브릭] {rubric_prompt('validation', 'assessment')}
모든 기준에 대해 다음 JSON만 출력하세요:
{{"items":[{{"criterion_id":"A-VAL-01","passed":true,"evidence":"판정 근거","revision_instruction":"실패 시 수정 지시"}}]}}"""
    ai_items = _dict_items(call_gemma_json(prompt).get("items", []))
    if not ai_items:
        ai_items = [{
            "criterion_id": "A-VAL-FORMAT", "passed": False,
            "evidence": "검증 응답 형식이 올바르지 않습니다.",
            "revision_instruction": "문항을 다시 검증하세요.",
        }]
    failed = [item["criterion_id"] for item in ai_items if not item.get("passed")]
    return {"validation": {
        "passed": not notes and not failed,
        "mechanical_notes": notes,
        "failed_ids": failed,
        "items": ai_items,
        "language_control": {
            "reading": state.get("reading_language_audit", {}),
            "writing": state.get("writing_language_audit", {}),
            "reading_revision_history": state.get("reading_language_revision_history", []),
            "writing_revision_history": state.get("writing_language_revision_history", []),
        },
    }}


def assessment_review(state: dict) -> dict:
    payload = interrupt({
        "stage": "assessment_review",
        "passage": state["passage"],
        "reading_items": state.get("reading_items", []),
        "writing_task": state.get("writing_task", {}),
        "writing_sentence_type": state["writing_sentence_type"],
        "validation": state.get("validation", {}),
        "reading_language_audit": state.get("reading_language_audit", {}),
        "reading_language_revision_history": state.get("reading_language_revision_history", []),
        "writing_language_audit": state.get("writing_language_audit", {}),
        "writing_language_revision_history": state.get("writing_language_revision_history", []),
        "generation_rubric": rubric_section("generation", "assessment"),
        "validation_rubric": rubric_section("validation", "assessment"),
        "approval_rubric": rubric_section("approval", "assessment"),
        "round_no": state.get("assessment_round", 1),
    })
    return {
        "assessment_decision": payload.get("decision", "reject"),
        "reject_note": "" if payload.get("decision") == "approve" else payload.get("note", ""),
        "assessment_regeneration_targets": payload.get("regeneration_targets", []),
        "reading_regeneration_indexes": payload.get("reading_regeneration_indexes", []),
        "writing_regeneration": payload.get("writing_regeneration", False),
        "assessment_approval_review": payload.get("approval_review", {}),
        "review_history": state.get("review_history", []) + [{
            "stage": "assessment", "decision": payload.get("decision", "reject"),
            "reasons": payload.get("approval_review", {}),
        }],
        "log": [f"[문항 검토] {payload.get('decision', 'reject')}"],
    }


def bump_assessment(state: dict) -> dict:
    return {"assessment_round": state.get("assessment_round", 1) + 1}


def publish(state: dict) -> dict:
    public = publish_assessment(state)
    return {
        "published_task_id": public["task_id"],
        "published_path": f"SQLite assessments/{public['task_id']}",
        "log": [f"[게시 완료] {public['task_id']}"],
    }
