"""SQLite 등급별 어휘 사전 조회 서비스."""

from __future__ import annotations

import re
import sqlite3

from app.core.config import DICTIONARY_DB

_KOREAN_TOKEN = re.compile(r"[가-힣]{2,}")

TASK_GRAMMAR_FORMS = {
    "sentence_completion": ["-고 싶다", "-고 있다", "-어 보다", "-으면"],
    "paragraph": ["-기 때문에", "-지만", "-은 후에", "-는 것 같다"],
    "practical": ["-으세요", "-어야 되다", "-어도 되다", "-기 전에"],
    "essay": ["-으므로", "-는 반면", "-더라도", "-기 위해", "-을수록"],
    "summary": ["-고3", "-은 후에", "-은 다음에", "-는 반면", "-기 때문에"],
    "opinion": ["-는 것 같다", "-지만", "-기 때문에", "-으면 좋겠다", "-는 반면"],
    "vocab_reuse": ["-고 싶다", "-어 보다", "-기 때문에", "-으면"],
}


def _connect() -> sqlite3.Connection:
    if not DICTIONARY_DB.exists():
        raise FileNotFoundError(
            f"어휘 사전이 없습니다: {DICTIONARY_DB}\n"
            "프로젝트 루트에서 `python tools/builders/build_dictionary.py`를 실행하세요."
        )
    conn = sqlite3.connect(DICTIONARY_DB)
    conn.row_factory = sqlite3.Row
    return conn


def lookup_word(word: str, max_grade: int = 6) -> list[dict]:
    """표제어를 정확히 조회한다."""
    with _connect() as conn:
        rows = conn.execute(
            """SELECT word, grade, part_of_speech, guide
               FROM vocabulary WHERE word = ? AND grade <= ? ORDER BY grade""",
            (word.strip(), max_grade),
        ).fetchall()
    return [dict(row) for row in rows]


def search_dictionary(
    query: str,
    max_grade: int,
    limit: int = 120,
) -> list[dict]:
    """주제·원문과 겹치는 표제어 및 길잡이말을 등급 범위 안에서 조회한다."""
    if max_grade not in range(1, 7):
        raise ValueError("max_grade는 1~6이어야 합니다.")

    tokens = list(dict.fromkeys(_KOREAN_TOKEN.findall(query)))
    with _connect() as conn:
        rows = conn.execute(
            """SELECT word, grade, part_of_speech, guide
               FROM vocabulary WHERE grade <= ? ORDER BY grade, word""",
            (max_grade,),
        ).fetchall()

    scored: list[tuple[int, int, str, dict]] = []
    for row in rows:
        item = dict(row)
        word = item["word"]
        guide = item["guide"]
        score = 0
        if len(word) >= 2 and word in query:
            score += 10
        for token in tokens:
            if token == word:
                score += 8
            elif len(word) >= 2 and (word in token or token in word):
                score += 3
            if token in guide:
                score += 2
        if score:
            scored.append((-score, item["grade"], word, item))

    scored.sort(key=lambda value: value[:3])
    return [value[3] for value in scored[:limit]]


def prompt_vocabulary(query: str, max_grade: int, limit: int = 120) -> tuple[str, int]:
    """생성 프롬프트에 넣을 관련 어휘만 간결한 문자열로 반환한다."""
    selected = search_dictionary(query, max_grade, limit)
    text = ", ".join(
        f"{item['word']}({item['part_of_speech']}, {item['grade']}급)"
        for item in selected[:limit]
    )
    return text, min(len(selected), limit)


def lookup_grammar(form: str, max_grade: int = 6) -> list[dict]:
    """대표형 또는 관련형에 포함된 문법 형태를 조회한다."""
    pattern = f"%{form.strip()}%"
    with _connect() as conn:
        rows = conn.execute(
            """SELECT sequence, grade, category, form, related_forms, meaning
               FROM grammar
               WHERE grade <= ? AND (form LIKE ? OR related_forms LIKE ?)
               ORDER BY grade, sequence""",
            (max_grade, pattern, pattern),
        ).fetchall()
    return [dict(row) for row in rows]


def grammar_for_task(task_type: str, max_grade: int, limit: int = 8) -> list[dict]:
    """과제 유형에 맞는 문법 중 목표 등급 이하 항목만 선택한다."""
    candidates = TASK_GRAMMAR_FORMS.get(task_type, TASK_GRAMMAR_FORMS["paragraph"])
    selected: list[dict] = []
    seen: set[tuple[int, int]] = set()
    for form in candidates:
        matches = lookup_grammar(form, max_grade)
        if not matches:
            continue
        item = matches[-1]
        key = (item["grade"], item["sequence"])
        if key not in seen:
            selected.append(item)
            seen.add(key)
        if len(selected) >= limit:
            break
    return selected


def prompt_grammar(task_type: str, max_grade: int, limit: int = 8) -> tuple[str, int]:
    """쓰기 생성에 사용할 등급 적합 문법 목록을 반환한다."""
    selected = grammar_for_task(task_type, max_grade, limit)
    text = ", ".join(
        f"{item['form']}({item['category']}, {item['grade']}급)"
        for item in selected
    )
    return text, len(selected)
