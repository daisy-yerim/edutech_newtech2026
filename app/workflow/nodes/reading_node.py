"""선택한 읽기 유형마다 정확히 한 문항을 생성한다."""

from app.core.llm import call_gemma_json
from app.services.dictionary import prompt_vocabulary
from app.services.generation_standards import question_types_prompt, standard_prompt
from app.services.language_control import adjust_language_document

DemoState = dict


def _one_type_prompt(state: DemoState, type_id: str, vocab_text: str) -> str:
    grade = state["grade"]
    revision = state.get("reject_note", "")
    return f"""당신은 한국어 읽기 평가 문항 개발자입니다.

[목표 등급]
{grade}급

[등급별 생성 기준]
{standard_prompt(grade, 'reading')}

[승인된 지문]
{state['passage']}

[생성할 유형]
{question_types_prompt([type_id])}

[권장 어휘]
{vocab_text}

[교수자 수정 요청]
{revision or '없음'}

위 유형의 문항을 정확히 1개만 만드세요. 선택지는 4개이고 정답은 선택지 중 하나와 글자까지 정확히 같아야 합니다.
[TOPIK형 교육자료 품질 기준]
- 먼저 정답 근거가 되는 지문의 문장 또는 문장 관계를 하나 정한 뒤 문항을 만드세요.
- 오답은 무관한 내용을 임의로 만들지 말고, 지문의 실제 단어·세부 정보를 사용해 `부분만 맞음`, `주체/대상 바꿈`, `원인/결과 바꿈`, `범위 과장` 중 서로 다른 오류 원리로 만드세요.
- 정답만 유난히 길거나 구체적이지 않게 네 선택지의 길이·문체·문법 형식을 맞추세요.
- 상식만으로 풀 수 있거나 지문을 읽지 않아도 답이 드러나는 선택지, 말이 안 되어 즉시 버릴 수 있는 오답을 금지합니다.
- 해설에는 정답의 지문 근거와 각 오답이 틀린 핵심 이유를 간결하게 포함해 복습 자료로 쓸 수 있게 하세요.
- 지문에 없는 새 사실을 정답 또는 해설의 근거로 추가하지 마세요.
다음 JSON 객체만 출력하세요.
{{
  "question_type": "{type_id}",
  "question": "문항 질문",
  "choices": ["선택지1", "선택지2", "선택지3", "선택지4"],
  "answer": "정답 선택지 원문",
  "explanation": "정답 근거를 포함한 해설"
}}"""


def _normalize_item(raw: dict, type_id: str) -> dict:
    # 모델이 예전 배열 형식을 반환해도 첫 문항을 받아들인다.
    if isinstance(raw.get("items"), list) and raw["items"]:
        raw = raw["items"][0]
    if not isinstance(raw, dict):
        raw = {}
    return {
        "question_type": type_id,
        "question": raw.get("question", ""),
        "choices": raw.get("choices", []),
        "answer": raw.get("answer", ""),
        "explanation": raw.get("explanation", ""),
    }


def reading_node(state: DemoState) -> dict:
    selected_types = state.get("reading_question_types") or [
        "topic", "main_idea", "title", "content_match"
    ]
    lookup_context = "\n".join([
        state.get("topic", ""), state.get("passage", ""), state.get("reject_note", "")
    ])
    vocab_text, _ = prompt_vocabulary(lookup_context, state["grade"])

    # 한 번에 여러 문항을 요청하면 모델이 일부를 누락할 수 있으므로 유형별로 호출한다.
    items = []
    for type_id in selected_types:
        item = {}
        for _ in range(2):
            raw = call_gemma_json(_one_type_prompt(state, type_id, vocab_text))
            item = _normalize_item(raw, type_id)
            if (item["question"] and len(item["choices"]) == 4
                    and item["answer"] in item["choices"] and item["explanation"]):
                break
        items.append(item)

    items, language_audit, language_revision_history = adjust_language_document(
        document=items,
        target_grade=state["grade"],
        task_type="paragraph",
        document_kind="읽기 문항",
        source_text=state.get("source_text", ""),
    )
    return {
        "reading_items": items,
        "reading_language_audit": language_audit,
        "reading_language_revision_history": language_revision_history,
        "log": [
            f"[읽기 문항 생성] 선택 {len(selected_types)}개 / 생성 {len(items)}개 "
            f"(라운드 {state.get('round_no', 1)})"
        ],
    }
