# -*- coding: utf-8 -*-
"""
extract_vocab.py — 국제 통용 한국어 표준 교육과정의 등급별 어휘 목록 추출

[사용법]
1. 프로젝트 루트에서 ingest.py를 실행해 output/chunks_*.json을 만든다.
2. VS Code에서 이 파일을 열고 `# %%` 셀을 위에서부터 실행한다.
   또는 터미널에서: python extract_vocab.py
3. 결과: data/processed/vocab_by_grade.json

PDF 표의 페이지 머리글은 다음 등급 헤더 뒤에도 이전 등급 항목을 포함한다.
따라서 `○ N급` 위치로 자르지 않고, 연속된 `번호+등급` 표식을 기준으로
각 레코드의 경계를 결정한다.
"""

# %% [셀 1] 설정
from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import re

OUTPUT_DIR = Path("data/reference")
OUTPUT_PATH = OUTPUT_DIR / "vocab_by_grade.json"

# ingest.py의 기본 설정 결과를 우선 사용한다. 없으면 다른 청크 결과를 찾는다.
PREFERRED_CHUNKS = OUTPUT_DIR / "chunks_500_50.json"
VOCAB_PAGE_FROM = 314
VOCAB_PAGE_TO = 471  # 472페이지부터 <부록 2> 문법 평정 목록

# PDF의 각 등급별 마지막 일련번호. 번호가 빠지면 즉시 오류로 알린다.
EXPECTED_COUNTS = {
    1: 735,
    2: 1100,
    3: 1655,
    4: 2200,
    5: 2365,
    6: 2580,
}


# %% [셀 2] 청크 파일에서 PDF 페이지 원문 복원
def find_chunks_path() -> Path:
    if PREFERRED_CHUNKS.exists():
        return PREFERRED_CHUNKS

    candidates = sorted(OUTPUT_DIR.glob("chunks_*.json"))
    if not candidates:
        raise FileNotFoundError(
            "output/chunks_*.json이 없습니다. 먼저 프로젝트 루트에서 "
            "ingest.py의 셀 1~6을 실행하세요."
        )
    return candidates[0]


def chunk_order(record: dict) -> int:
    """chunk_id 끝의 `_c번호`를 정렬 키로 사용한다."""
    match = re.search(r"_c(\d+)$", record.get("chunk_id", ""))
    if not match:
        raise ValueError(f"PDF 청크 번호를 읽을 수 없습니다: {record.get('chunk_id')}")
    return int(match.group(1))


def merge_overlapping_texts(texts: list[str]) -> str:
    """인접 청크의 동일한 겹침 부분을 한 번만 남겨 페이지를 복원한다."""
    if not texts:
        return ""

    merged = texts[0]
    for text in texts[1:]:
        max_overlap = min(len(merged), len(text), 2000)
        overlap = 0
        for size in range(max_overlap, 0, -1):
            if merged.endswith(text[:size]):
                overlap = size
                break
        merged += text[overlap:]
    return merged


def load_vocab_pages(chunks_path: Path) -> str:
    with chunks_path.open("r", encoding="utf-8") as file:
        chunks = json.load(file)

    pages: dict[int, list[dict]] = defaultdict(list)
    for chunk in chunks:
        page = chunk.get("page")
        if (
            chunk.get("doc_type") == "기준문서"
            and isinstance(page, int)
            and VOCAB_PAGE_FROM <= page <= VOCAB_PAGE_TO
        ):
            pages[page].append(chunk)

    missing_pages = [
        page
        for page in range(VOCAB_PAGE_FROM, VOCAB_PAGE_TO + 1)
        if page not in pages
    ]
    if missing_pages:
        raise ValueError(f"어휘 목록 페이지가 누락되었습니다: {missing_pages}")

    page_texts = []
    for page in range(VOCAB_PAGE_FROM, VOCAB_PAGE_TO + 1):
        ordered = sorted(pages[page], key=chunk_order)
        text = merge_overlapping_texts([item["text"] for item in ordered])
        # PDF 쪽번호와 페이지마다 반복되는 표 머리글을 제거한다.
        text = re.sub(r"^\s*-\s*\d+\s*-\s*", "", text)
        text = text.replace("번호등급어휘품사길잡이말", "")
        page_texts.append(text)

    return "\n".join(page_texts)


chunks_path = find_chunks_path()
vocab_text = load_vocab_pages(chunks_path)
print(f"입력 청크: {chunks_path}")
print(f"어휘 표 복원 범위: PDF {VOCAB_PAGE_FROM}~{VOCAB_PAGE_TO}페이지")
print(f"복원 텍스트 길이: {len(vocab_text):,}자")


# %% [셀 3] 연속 번호로 레코드 분리 + 품사 앵커로 열 분리
# 긴 품사를 먼저 두어 '의존명사'를 '명사'로 잘못 자르지 않게 한다.
POS_COMPONENTS = [
    "의존명사",
    "보조형용사",
    "보조동사",
    "관형사",
    "대명사",
    "형용사",
    "감탄사",
    "줄어든꼴",
    "줄어든말",
    "명사",
    "동사",
    "부사",
    "수사",
    "조사",
    "접사",
]


def spaced_pattern(word: str) -> str:
    """PDF가 '관 형 사'처럼 글자 사이를 띄워도 일치하게 만든다."""
    return r"\s*".join(map(re.escape, word))


pos_component_pattern = "(?:" + "|".join(
    spaced_pattern(pos) for pos in POS_COMPONENTS
) + ")"
POS_PATTERN = re.compile(
    rf"(?P<pos>{pos_component_pattern}(?:\s*[/∙·‧・.]\s*{pos_component_pattern})*)"
)

# PDF의 셀 안 줄바꿈 때문에 어휘·품사·길잡이말의 추출 순서가 뒤섞인 행.
# 일반 규칙으로 복구할 수 없는 11개만 원문 표를 따라 명시적으로 교정한다.
MALFORMED_ROW_OVERRIDES = {
    (1, 516): {"어휘": "육/육", "품사": "수사/관형사", "길잡이말": "숫자"},
    (3, 158): {"어휘": "그제/그제", "품사": "명사/부사", "길잡이말": "그저께"},
    (3, 1013): {
        "어휘": "엊그제/엊그제",
        "품사": "부사/명사",
        "길잡이말": "엊그제 아침",
    },
    (3, 1280): {
        "어휘": "전국적/전국적",
        "품사": "관형사/명사",
        "길잡이말": "전국적 규모",
    },
    (5, 1209): {
        "어휘": "시간적/시간적",
        "품사": "관형사/명사",
        "길잡이말": "시간적 순서",
    },
    (5, 1891): {
        "어휘": "쯧쯧/쯧쯧",
        "품사": "부사/감탄사",
        "길잡이말": "혀를 쯧쯧 차다",
    },
    (6, 79): {
        "어휘": "강제적/강제적",
        "품사": "관형사/명사",
        "길잡이말": "강제적 조치",
    },
    (6, 607): {"어휘": "대거/대거", "품사": "부사/명사", "길잡이말": "대거 투입"},
    (6, 874): {
        "어휘": "무차별적/무차별적",
        "품사": "관형사/명사",
        "길잡이말": "무차별적 수용",
    },
    (6, 1701): {
        "어휘": "유동적/유동적",
        "품사": "관형사/명사",
        "길잡이말": "유동적 상황",
    },
    (6, 1961): {
        "어휘": "정서적/정서적",
        "품사": "관형사/명사",
        "길잡이말": "정서적 교감",
    },
}


def normalize_pos(raw_pos: str) -> str:
    return re.sub(r"\s+", "", raw_pos).strip()


def normalize_vocab(raw_vocab: str) -> str:
    """동형어 번호(가격02 등)는 제거하되 구분자와 접사 표시는 보존한다."""
    compact = re.sub(r"\s+", "", raw_vocab).strip()
    parts = re.split(r"([/∙·‧・.])", compact)
    normalized = [re.sub(r"(?:00|0[1-9]|[1-9]\d)$", "", part) for part in parts]
    return "".join(normalized)


def clean_guide(raw_guide: str) -> str:
    return re.sub(r"\s+", " ", raw_guide).strip()


def marker_pattern(number: int, grade: int) -> re.Pattern[str]:
    # 앞 숫자의 일부를 번호로 오인하지 않도록 바로 앞이 숫자가 아니어야 한다.
    return re.compile(rf"(?<!\d){number}\s*{grade}\s*급")


def find_marker(text: str, number: int, grade: int, start: int) -> re.Match[str]:
    match = marker_pattern(number, grade).search(text, start)
    if not match:
        raise ValueError(
            f"{grade}급 {number}번의 시작 표식을 찾지 못했습니다 "
            f"(검색 위치: {start:,})."
        )
    return match


def parse_vocab(text: str) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = {}
    search_from = text.find("<부록 1>")
    if search_from < 0:
        raise ValueError("<부록 1> 어휘 평정 목록 시작점을 찾지 못했습니다.")

    for grade, expected_count in EXPECTED_COUNTS.items():
        grade_key = f"{grade}급"
        records: list[dict[str, str]] = []

        for number in range(1, expected_count + 1):
            current = find_marker(text, number, grade, search_from)

            if number < expected_count:
                following = find_marker(text, number + 1, grade, current.end())
                body_end = following.start()
            elif grade < 6:
                following = find_marker(text, 1, grade + 1, current.end())
                body_end = following.start()
            else:
                appendix_2 = text.find("<부록 2>", current.end())
                body_end = appendix_2 if appendix_2 >= 0 else len(text)
                following = None

            body = text[current.end():body_end]
            # 등급 헤더는 실제 등급 전환보다 먼저 인쇄되므로 레코드 내부에서 제거한다.
            body = re.sub(r"○\s*[1-6]\s*급", "", body)
            body = body.strip()

            override = MALFORMED_ROW_OVERRIDES.get((grade, number))
            if override:
                records.append(override.copy())
                search_from = following.start() if following else body_end
                continue

            # '조사03명사조사 결과'처럼 어휘 자체가 품사명과 같은 경우가 있다.
            # 레코드 맨 앞에서 시작하는 일치는 어휘로 보고 건너뛴다.
            pos_match = POS_PATTERN.search(body, 1)
            if not pos_match:
                raise ValueError(
                    f"{grade_key} {number}번에서 품사를 찾지 못했습니다: {body[:100]!r}"
                )

            vocab = normalize_vocab(body[:pos_match.start()])
            pos = normalize_pos(pos_match.group("pos"))
            guide = clean_guide(body[pos_match.end():])
            if not vocab:
                raise ValueError(
                    f"{grade_key} {number}번의 어휘가 비어 있습니다: {body[:100]!r}"
                )

            records.append({"어휘": vocab, "품사": pos, "길잡이말": guide})
            search_from = following.start() if following else body_end

        result[grade_key] = records

    return result


vocab_by_grade = parse_vocab(vocab_text)


# %% [셀 4] 검증 + JSON 저장
def validate_vocab(data: dict[str, list[dict[str, str]]]) -> None:
    for grade, expected_count in EXPECTED_COUNTS.items():
        grade_key = f"{grade}급"
        records = data.get(grade_key, [])
        if len(records) != expected_count:
            raise ValueError(
                f"{grade_key} 항목 수 오류: 예상 {expected_count:,}, 실제 {len(records):,}"
            )

        for index, record in enumerate(records, start=1):
            if set(record) != {"어휘", "품사", "길잡이말"}:
                raise ValueError(f"{grade_key} {index}번 필드 구성이 잘못되었습니다.")
            if not record["어휘"] or not record["품사"]:
                raise ValueError(f"{grade_key} {index}번 필수 값이 비어 있습니다: {record}")
            if re.search(r"\d", record["어휘"]):
                raise ValueError(f"{grade_key} {index}번 어휘에 동형어 번호가 남았습니다: {record}")
            if re.search(r"[/∙·‧・.]$", record["어휘"]):
                raise ValueError(f"{grade_key} {index}번 어휘 끝에 구분자가 남았습니다: {record}")
            if re.match(r"^[\/∙·‧・.]", record["길잡이말"]):
                raise ValueError(f"{grade_key} {index}번 길잡이말 열이 어긋났습니다: {record}")


validate_vocab(vocab_by_grade)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
with OUTPUT_PATH.open("w", encoding="utf-8") as file:
    json.dump(vocab_by_grade, file, ensure_ascii=False, indent=2)

print("\n===== 추출 결과 =====")
for grade_key, records in vocab_by_grade.items():
    duplicate_count = sum(
        count - 1 for count in Counter(item["어휘"] for item in records).values() if count > 1
    )
    print(
        f"{grade_key}: {len(records):,}개 "
        f"(같은 등급 내 중복 표기 {duplicate_count:,}개)"
    )
    print("  처음 2개:", records[:2])
    print("  마지막 2개:", records[-2:])

total = sum(len(records) for records in vocab_by_grade.values())
print(f"\n총 {total:,}개 저장 완료 -> {OUTPUT_PATH}")
