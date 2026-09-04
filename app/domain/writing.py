# %%
"""
writing_config.py
─────────────────
쓰기 과제 생성기(writing_generator.py)와 채점기(writing_grader.py)가
공유하는 '과제 유형 정의'와 'TOPIK 기반 채점 루브릭'을 한 곳에 모아둔 설정 파일.

여기 한 곳만 수정하면 생성·채점 양쪽에 동일하게 반영됩니다.
교수자가 기준을 바꾸고 싶을 때(예: 배점 조정, 유형 추가) 이 파일만 고치면 됩니다.
"""

# ──────────────────────────────────────────────────────────────
# 1. 쓰기 과제 유형 정의
# ──────────────────────────────────────────────────────────────
# 각 유형마다:
#   - label            : 사람이 읽는 이름
#   - recommended_grades : 이 유형이 적절한 등급대 (참고용, 강제는 아님)
#   - target_length    : 학습자가 써야 할 대략적 분량 (프롬프트에 안내)
#   - instruction      : Gemma에게 "이런 성격의 과제를 내라"고 지시하는 설명
#   - rubric_keys      : 이 유형에 적용할 루브릭 항목 (아래 RUBRICS의 키)

TASK_TYPES = {
    "sentence_completion": {
        "label": "문장 완성 / 짧은 응답",
        "recommended_grades": [1, 2, 3],
        "target_length": "각 문항당 1~2문장 (총 3~4문항)",
        "instruction": (
            "빈칸이 포함된 문장을 완성하거나, 짧은 질문에 한두 문장으로 답하는 "
            "초급 수준의 쓰기 문항을 낸다. 실제 생활 상황(자기소개, 하루 일과, "
            "좋아하는 것 등)을 소재로 한다."
        ),
        "rubric_keys": ["content_short", "language_use"],
        "requires_passage": False,
    },
    "paragraph": {
        "label": "단락 쓰기 (지정 주제)",
        "recommended_grades": [3, 4],
        "target_length": "150~300자 내외의 한 단락",
        "instruction": (
            "하나의 지정된 주제에 대해 한 단락(중심 문장 + 뒷받침 문장 몇 개)을 "
            "쓰도록 하는 과제를 낸다. 주제와 함께, 반드시 포함해야 할 내용 요소를 "
            "2~3개 제시한다."
        ),
        "rubric_keys": ["content", "organization", "language_use"],
        "requires_passage": False,
    },
    "practical": {
        "label": "실용문 (이메일 · 안내문 등)",
        "recommended_grades": [3, 4, 5],
        "target_length": "200~400자 내외의 완성된 실용문",
        "instruction": (
            "이메일, 안내문, 문자 메시지, 초대장 같은 실용적인 글을 쓰도록 하는 "
            "과제를 낸다. 상황(누구에게, 왜 쓰는지)과 반드시 담아야 할 정보 항목을 "
            "명확히 제시한다. 격식/비격식 여부도 지정한다."
        ),
        "rubric_keys": ["content", "organization", "language_use", "register"],
        "requires_passage": False,
    },
    "essay": {
        "label": "자유 작문 / 에세이",
        "recommended_grades": [5, 6],
        "target_length": "500~700자 내외의 글",
        "instruction": (
            "하나의 논제(찬반, 의견 제시, 경험 서술 등)에 대해 자신의 생각을 "
            "논리적으로 서술하는 중고급 에세이 과제를 낸다. 도입-전개-마무리 구조를 "
            "요구하고, 구체적 근거나 예시를 들도록 안내한다."
        ),
        "rubric_keys": ["content", "organization", "language_use", "coherence"],
        "requires_passage": False,
    },
}


# ──────────────────────────────────────────────────────────────
# 1-1. 읽기 지문 연계 쓰기 과제 유형 (신규)
# ──────────────────────────────────────────────────────────────
# 위 TASK_TYPES와 달리, 이 유형들은 반드시 '읽기 지문 원문'을 프롬프트에
# 함께 넣어야 한다 (requires_passage: True). writing_generator.py에서
# PASSAGE_PATH를 지정하면 이 딕셔너리에서 유형을 찾는다.
#
# 세 가지 연계 방식을 모두 지원 — 교수자가 상황에 맞게 골라 쓴다:
#   - summary      : 지문 요약하기
#   - opinion      : 지문에 대한 의견 · 감상 쓰기
#   - vocab_reuse  : 지문 속 표현 · 어휘를 활용해 짧은 글 쓰기

LINKED_TASK_TYPES = {
    "summary": {
        "label": "지문 요약하기",
        "recommended_grades": [3, 4, 5],
        "target_length": "지문의 1/3~1/2 분량 (3~5문장)",
        "instruction": (
            "아래 제시된 읽기 지문을 학습자가 이미 읽었다고 가정하고, 지문의 핵심 "
            "내용을 자신의 말로 요약하는 과제를 낸다. 지문 문장을 그대로 베끼지 "
            "말고 자신의 표현으로 정리하도록 안내한다."
        ),
        "rubric_keys": ["content", "organization", "language_use"],
        "requires_passage": True,
    },
    "opinion": {
        "label": "지문에 대한 의견 · 감상 쓰기",
        "recommended_grades": [3, 4, 5, 6],
        "target_length": "200~400자",
        "instruction": (
            "아래 제시된 읽기 지문을 읽고, 그 내용에 대한 자신의 생각이나 느낌을 "
            "밝히는 과제를 낸다. 지문 주제와 관련해 찬성/반대, 공감/비공감, 자신의 "
            "경험과의 연결 등 구체적인 관점을 요구한다."
        ),
        "rubric_keys": ["content", "organization", "language_use", "coherence"],
        "requires_passage": True,
    },
    "vocab_reuse": {
        "label": "지문 속 표현 · 어휘 활용해 쓰기",
        "recommended_grades": [2, 3, 4],
        "target_length": "100~250자",
        "instruction": (
            "아래 제시된 읽기 지문에 나온 핵심 어휘나 표현 중 일부를 반드시 사용해 "
            "짧은 글을 쓰는 과제를 낸다. 지문에서 실제로 활용해야 할 표현 3~5개를 "
            "과제 지시문에 구체적으로 지정한다."
        ),
        "rubric_keys": ["content_short", "language_use"],
        "requires_passage": True,
    },
}

# 생성기 · 채점기는 이 통합 딕셔너리를 통해 유형을 조회한다
# (일반 유형 + 연계 유형을 키 충돌 없이 합침)
ALL_TASK_TYPES = {**TASK_TYPES, **LINKED_TASK_TYPES}


# ──────────────────────────────────────────────────────────────
# 2. TOPIK 기반 채점 루브릭
# ──────────────────────────────────────────────────────────────
# TOPIK 쓰기의 3대 평가 범주(내용 및 과제 수행 / 글의 전개 구조 / 언어 사용)를
# 참고해 구성. 유형별로 필요한 항목만 rubric_keys로 골라 씁니다.
#
# 각 항목:
#   - label       : 범주 이름
#   - max_score   : 배점
#   - description : 채점자(Gemma)에게 주는 평가 관점
#   - levels      : 점수대별 판단 기준 (상/중/하) — 채점 일관성을 높이기 위함

RUBRICS = {
    "content_short": {
        "label": "내용 및 과제 수행",
        "max_score": 5,
        "description": "질문·빈칸에 맞는 내용을 정확히 썼는가, 요구한 문항 수를 채웠는가.",
        "levels": {
            "상 (4~5)": "모든 문항에 상황에 맞는 내용을 정확하게 작성함.",
            "중 (2~3)": "일부 문항만 수행했거나 내용이 부분적으로 어긋남.",
            "하 (0~1)": "과제를 거의 수행하지 못했거나 무관한 내용.",
        },
    },
    "content": {
        "label": "내용 및 과제 수행",
        "max_score": 10,
        "description": "주제에 맞는 내용인가, 요구된 내용 요소를 모두 포함했는가, 분량을 지켰는가.",
        "levels": {
            "상 (8~10)": "주제에 충실하고 요구 요소를 모두 담았으며 분량도 적절함.",
            "중 (4~7)": "주제는 맞으나 일부 요소 누락 또는 분량 부족.",
            "하 (0~3)": "주제에서 벗어나거나 요구 요소 대부분 누락.",
        },
    },
    "organization": {
        "label": "글의 전개 구조",
        "max_score": 10,
        "description": "글의 구성이 논리적인가, 문단·문장 간 연결이 자연스러운가.",
        "levels": {
            "상 (8~10)": "도입-전개-마무리가 뚜렷하고 흐름이 매끄러움.",
            "중 (4~7)": "구성은 있으나 일부 연결이 어색하거나 단조로움.",
            "하 (0~3)": "구성이 없거나 문장이 뒤섞여 이해가 어려움.",
        },
    },
    "language_use": {
        "label": "언어 사용 (어휘 · 문법)",
        "max_score": 10,
        "description": (
            "해당 등급 수준의 어휘·문법을 정확하고 다양하게 사용했는가. "
            "특히 '등급 범위를 벗어난 과도하게 어려운 표현'과 '맞춤법·조사 오류'를 함께 본다."
        ),
        "levels": {
            "상 (8~10)": "등급에 맞는 어휘·문법을 정확하고 자연스럽게 구사함.",
            "중 (4~7)": "의미는 통하나 오류가 다소 있거나 표현이 단조로움.",
            "하 (0~3)": "오류가 잦아 의미 전달이 어려움.",
        },
    },
    "register": {
        "label": "격식 · 상황 적절성",
        "max_score": 5,
        "description": "요구된 격식(높임/반말, 공식/비공식)과 글의 형식(이메일 등)을 지켰는가.",
        "levels": {
            "상 (4~5)": "상황에 맞는 격식과 형식을 일관되게 지킴.",
            "중 (2~3)": "격식이 일부 흔들리거나 형식 요소 일부 누락.",
            "하 (0~1)": "격식·형식을 거의 지키지 못함.",
        },
    },
    "coherence": {
        "label": "응집성 · 논리성",
        "max_score": 5,
        "description": "주장과 근거가 논리적으로 이어지는가, 접속·지시 표현을 적절히 썼는가.",
        "levels": {
            "상 (4~5)": "주장-근거가 명확히 연결되고 논리가 탄탄함.",
            "중 (2~3)": "논리는 있으나 비약이나 반복이 보임.",
            "하 (0~1)": "논리적 연결이 약하거나 근거가 없음.",
        },
    },
}


# ──────────────────────────────────────────────────────────────
# 3. 보조 함수
# ──────────────────────────────────────────────────────────────
def get_task_type(type_key: str) -> dict:
    """
    유형 키로 과제 유형 정의를 가져온다. 일반 유형(TASK_TYPES)과
    읽기 지문 연계 유형(LINKED_TASK_TYPES)을 모두 조회한다.
    잘못된 키면 안내와 함께 에러.
    """
    if type_key not in ALL_TASK_TYPES:
        valid = ", ".join(ALL_TASK_TYPES.keys())
        raise KeyError(f"알 수 없는 과제 유형: '{type_key}'. 사용 가능: {valid}")
    return ALL_TASK_TYPES[type_key]


def requires_passage(type_key: str) -> bool:
    """이 유형이 읽기 지문 원문을 반드시 함께 필요로 하는지 여부."""
    return get_task_type(type_key).get("requires_passage", False)


def get_rubric_for_task(type_key: str) -> dict:
    """해당 과제 유형에 적용할 루브릭 항목들만 모아서 반환한다."""
    task = get_task_type(type_key)
    return {k: RUBRICS[k] for k in task["rubric_keys"]}


def total_max_score(type_key: str) -> int:
    """해당 과제 유형의 만점(루브릭 항목 배점 합계)."""
    return sum(r["max_score"] for r in get_rubric_for_task(type_key).values())


def format_rubric_text(type_key: str) -> str:
    """
    루브릭을 프롬프트에 넣기 좋은 텍스트로 변환.
    생성기(참고용)와 채점기(채점 기준) 양쪽에서 사용한다.
    """
    lines = []
    rubric = get_rubric_for_task(type_key)
    for key, r in rubric.items():
        lines.append(f"■ {r['label']} (배점 {r['max_score']}점)")
        lines.append(f"   - 평가 관점: {r['description']}")
        for level, desc in r["levels"].items():
            lines.append(f"   - {level}: {desc}")
        lines.append("")
    lines.append(f"총점: {total_max_score(type_key)}점 만점")
    return "\n".join(lines)


# %%
# 단독 실행 시 설정 내용을 미리보기 (검증용)
if __name__ == "__main__":
    print("=== 독립형 과제 유형 (지문 불필요) ===")
    for key, t in TASK_TYPES.items():
        print(f"  [{key}] {t['label']}  (권장 등급: {t['recommended_grades']}, "
              f"만점 {total_max_score(key)}점)")

    print("\n=== 읽기 지문 연계형 과제 유형 (지문 필요) ===")
    for key, t in LINKED_TASK_TYPES.items():
        print(f"  [{key}] {t['label']}  (권장 등급: {t['recommended_grades']}, "
              f"만점 {total_max_score(key)}점)")

    print("\n=== 예시: 'summary'(지문 연계) 유형 루브릭 ===")
    print(format_rubric_text("summary"))
