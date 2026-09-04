from typing import TypedDict


class LearnerState(TypedDict, total=False):
    task_id: str
    reading_answers: dict[str, str]
    writing_answer: str
    public_task: dict
    grading_key: dict
    reading_result: dict
    writing_result: dict
    final_result: dict
    submission_id: str
