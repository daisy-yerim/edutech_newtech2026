from tools.experiments.run_ontology_validation_loop import (
    normalize_reading_item,
    ontology_validate,
    strip_model_heading,
)


def test_numbered_answer_is_resolved_to_exact_choice_text():
    item = normalize_reading_item({
        "choices": ["첫째", "둘째", "셋째", "넷째"],
        "answer": "2",
    })
    assert item["answer"] == "둘째"


def test_interleaved_choice_numbers_are_removed():
    item = normalize_reading_item({
        "choices": ["1", "첫째", "2", "둘째", "3", "셋째", "4", "넷째"],
        "answer": "3",
    })
    assert item["choices"] == ["첫째", "둘째", "셋째", "넷째"]
    assert item["answer"] == "셋째"


def test_paraphrased_answer_is_snapped_to_near_identical_choice():
    item = normalize_reading_item({
        "choices": [
            "약 50개의 기업이 정책에 참여했다.",
            "기업이 정책에 참여하지 않았다.",
            "정부가 정책을 중단했다.",
            "참여 기업 수는 공개되지 않았다.",
        ],
        "answer": "약 50개 이상의 기업이 정책에 참여했다.",
    })
    assert item["answer"] == item["choices"][0]


def test_ontology_gate_requires_length_grade_resources_and_relations():
    result = ontology_validate({
        "source_key": "test_source",
        "grade": 3,
        "text_type": "짧은 기사",
        "passage": "가" * 250,
        "vocabulary_audit": {"violations": [], "blocked_unknown_tokens": []},
    })
    assert result["passed"]


def test_ontology_gate_returns_repairable_failures():
    result = ontology_validate({
        "source_key": "test_source",
        "grade": 3,
        "text_type": "짧은 기사",
        "passage": "가" * 320,
        "vocabulary_audit": {
            "violations": [{"word": "접종", "grade": 6}],
            "blocked_unknown_tokens": [],
        },
    })
    assert result["failed_ids"] == ["O-VAL-LENGTH", "O-VAL-GRADE-RESOURCE"]
    grade_resource = next(
        item for item in result["items"]
        if item["criterion_id"] == "O-VAL-GRADE-RESOURCE"
    )
    assert "접종(6급)" in grade_resource["evidence"]


def test_model_heading_is_removed_before_length_validation():
    assert strip_model_heading("**제목**\n\n본문입니다.") == "본문입니다."
    verbose = "보완 설명\n---\n**최종 출력물 (120자 목표):**\n\n최종 본문입니다."
    assert strip_model_heading(verbose) == "최종 본문입니다."


def test_declared_source_term_must_appear_but_is_exempt_from_grade_failure():
    result = ontology_validate({
        "source_key": "energy_saving",
        "grade": 3,
        "text_type": "짧은 기사",
        "source_terms": ["에너지"],
        "passage": "가" * 250,
        "vocabulary_audit": {
            "violations": [{"word": "에너지", "grade": 4}],
            "blocked_unknown_tokens": [],
        },
    })
    assert result["failed_ids"] == ["O-VAL-SOURCE-TERM-USED"]
