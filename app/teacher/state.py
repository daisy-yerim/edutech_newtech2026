from typing import Annotated, TypedDict
import operator


class TeacherState(TypedDict, total=False):
    uploaded_filename: str
    source_text: str
    teacher_id: str
    teacher_name: str
    grade: int
    topic: str
    category_id: str
    category_label: str
    passage: str
    vocabulary_audit: dict
    vocabulary_revision_history: list[dict]
    passage_validation: dict
    passage_regeneration_targets: list[str]
    passage_approval_review: dict
    reading_question_types: list[str]
    writing_sentence_type: str
    reading_items: list[dict]
    reading_language_audit: dict
    reading_language_revision_history: list[dict]
    writing_task: dict
    writing_language_audit: dict
    writing_language_revision_history: list[dict]
    validation: dict
    assessment_regeneration_targets: list[str]
    reading_regeneration_indexes: list[int]
    writing_regeneration: bool
    assessment_approval_review: dict
    review_history: list[dict]
    passage_decision: str
    assessment_decision: str
    reject_note: str
    passage_round: int
    assessment_round: int
    published_task_id: str
    published_path: str
    log: Annotated[list[str], operator.add]


def initial_teacher_state(**values) -> TeacherState:
    return {
        **values,
        "source_text": "",
        "passage_round": 1,
        "assessment_round": 1,
        "reject_note": "",
        "passage_regeneration_targets": [],
        "assessment_regeneration_targets": [],
        "reading_regeneration_indexes": [],
        "writing_regeneration": False,
        "review_history": [],
        "log": [],
    }
