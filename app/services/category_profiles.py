"""Topic choices used by the teacher UI.

These labels are plain UI metadata and are not backed by corpus statistics.
"""

from functools import lru_cache

TOPIC_CATEGORIES = [
    {"id": "social", "label": "사회"},
    {"id": "lifestyle_health", "label": "생활·건강"},
    {"id": "it_science", "label": "IT·과학"},
    {"id": "finance", "label": "경제·금융"},
    {"id": "history", "label": "역사"},
    {"id": "culture", "label": "문화"},
]


@lru_cache(maxsize=1)
def category_manifest() -> dict:
    return {"categories": TOPIC_CATEGORIES}


@lru_cache(maxsize=8)
def category_profile(category_id: str) -> dict:
    entry = next((item for item in TOPIC_CATEGORIES if item["id"] == category_id), None)
    if entry is None:
        raise ValueError(f"없는 주제입니다: {category_id}")
    return {"category": entry}


def sentence_type_profile(category_id: str, sentence_type: str) -> dict:
    """Compatibility result without corpus-derived statistics or examples."""
    return category_profile(category_id)
