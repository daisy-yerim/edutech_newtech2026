from unittest.mock import patch

from app.services.language_control import (
    adjust_language_document,
    audit_language,
)
from app.services.vocabulary_control import (
    audit_vocabulary,
    clean_revised_passage,
    polish_beginner_topik_flow,
    polish_passage_naturalness,
)
from tools.experiments.run_passage_grade_loop import (
    BEGINNER_KEYWORD_CONTEXTS,
    BEGINNER_SOURCE_KEYWORDS,
)


READING = [{
    "question_type": "topic",
    "question": "반려동물 동반 음식점의 위생 관리 기준은 무엇입니까?",
    "choices": ["개와 고양이", "모든 동물", "새와 토끼", "알 수 없다"],
    "answer": "개와 고양이",
    "explanation": "글에 직접 제시되어 있다.",
}]


def test_vocabulary_audit_gets_less_restrictive_by_grade():
    counts = [
        audit_language(READING, grade, "paragraph")["vocabulary"]["violation_count"]
        for grade in range(1, 7)
    ]
    assert counts == sorted(counts, reverse=True)
    assert counts[0] > counts[-1]


def test_rejects_revision_that_breaks_answer_choice_consistency():
    broken = [{
        **READING[0],
        "answer": "선택지에 없는 답",
    }]
    with patch(
        "app.services.language_control.call_gemma_json",
        return_value={"document": broken},
    ):
        result, _, history = adjust_language_document(
            READING, 1, "paragraph", "읽기 문항"
        )
    assert result == READING
    assert history and history[0]["accepted"] is False


def test_language_audit_records_grammar_control_mode():
    audit = audit_language(READING, 3, "paragraph")
    assert audit["grammar"]["mode"] == "grade_profile_constrained"
    assert audit["grammar"]["deterministic_postcheck"] is False


def test_grade_1_blocks_every_unregistered_lexical_token():
    audit = audit_vocabulary("덮개가 있다", 1)
    blocked = {item["word"] for item in audit["blocked_unknown_tokens"]}
    assert "덮개" in blocked
    assert "있다" not in blocked  # elementary TOPIK-I audit exception


def test_grade_3_records_unregistered_common_noun_without_blocking():
    audit = audit_vocabulary("덮개가 있다", 3)
    assert "덮개" in audit["unknown_tokens"]
    assert audit["blocked_unknown_noun_count"] == 0


def test_revision_output_keeps_only_text_after_correction_marker():
    output = "원래 지문입니다.\n\n(교정 결과)\n수정한 지문입니다."
    assert clean_revised_passage(output) == "수정한 지문입니다."


def test_revision_output_removes_model_audit_commentary():
    output = "저는 공부합니다.\n\n(※ 참고: 이 문장은 교정 결과입니다.)"
    assert clean_revised_passage(output) == "저는 공부합니다."


def test_revision_output_removes_trailing_reconstruction_commentary():
    output = "전기를 아껴야 합니다. (원문 내용과 핵심 의미를 유지하면서 2급 이하 어휘로 재구성하였습니다.)"
    assert clean_revised_passage(output) == "전기를 아껴야 합니다."


def test_revision_output_removes_bracketed_model_title():
    output = "[전기를 아껴요]\n\n불을 꺼 주세요."
    assert clean_revised_passage(output) == "불을 꺼 주세요."


def test_beginner_flow_repair_accepts_exact_bounded_sentence_array():
    candidate = {
        "sentences": [
            "민수 씨는 사무실에 있습니다.",
            "이제 집에 가려고 합니다.",
            "방에 불이 켜져 있어서 불을 끕니다.",
            "불을 끄고 집에 갑니다.",
        ]
    }
    with patch(
        "app.services.vocabulary_control.call_gemma_json",
        return_value=candidate,
    ):
        passage, _, history = polish_beginner_topik_flow(
            passage="한 문장. 두 문장. 세 문장. 네 문장. 다섯 문장. 여섯 문장.",
            target_grade=1,
            source_text="사무실에서 쓰지 않는 불 끄기",
            min_chars=1,
            max_chars=200,
        )
    assert passage.count(".") == 4
    assert history["accepted"] is True


def test_grade_1_recovers_derived_adjective_lemma():
    audit = audit_vocabulary("방이 깨끗합니다", 1)
    assert "깨끗" not in audit["unknown_tokens"]
    assert "깨끗하다" not in audit["unknown_tokens"]


def test_naturalness_revision_is_rejected_when_unknown_word_returns():
    with patch(
        "app.services.vocabulary_control.call_gemma",
        return_value="덮개가 있다.",
    ):
        passage, _, history = polish_passage_naturalness(
            passage="저는 학교에 갑니다.",
            target_grade=1,
            source_text="학교 생활",
            min_chars=1,
            max_chars=100,
        )
    assert passage == "저는 학교에 갑니다."
    assert history["attempted"] is True
    assert history["accepted"] is False


def test_grade_1_naturalness_revision_rejects_too_many_sentences():
    revised = "저는 학교에 갑니다. 친구를 만납니다. 같이 공부합니다. 밥을 먹습니다. 집에 갑니다. 잠을 잡니다."
    with patch(
        "app.services.vocabulary_control.call_gemma",
        return_value=revised,
    ):
        passage, _, history = polish_passage_naturalness(
            passage="학교에서 친구를 만납니다. 같이 공부합니다. 그리고 집에 갑니다.",
            target_grade=1,
            source_text="학교 생활",
            min_chars=1,
            max_chars=200,
        )
    assert passage != revised
    assert history["accepted"] is False
    assert "문장 수" in history["reason"]


def test_naturalness_revision_rejects_fluent_topic_drift():
    with patch(
        "app.services.vocabulary_control.call_gemma",
        return_value="시장에서 사과를 삽니다. 사과는 달고 맛있습니다. 집에서 사과를 먹습니다.",
    ):
        passage, _, history = polish_passage_naturalness(
            passage="친구와 식당에 갑니다. 식당에서 비빔밥을 먹습니다. 같이 점심을 먹어서 좋습니다.",
            target_grade=1,
            source_text="친구와 식당에서 점심 먹기",
            min_chars=1,
            max_chars=200,
        )
    assert passage.startswith("친구와 식당")
    assert history["accepted"] is False
    assert "핵심 내용어 유지율" in history["reason"]


def test_beginner_source_keywords_are_inside_target_grade():
    for source_id, source_grades in BEGINNER_SOURCE_KEYWORDS.items():
        for grade, keyword in source_grades.items():
            audit = audit_vocabulary(keyword, grade)
            assert audit["violation_count"] == 0
            assert audit["blocked_unknown_token_count"] == 0
            assert BEGINNER_KEYWORD_CONTEXTS[source_id][grade]
