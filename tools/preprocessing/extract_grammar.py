"""교육과정 PDF의 <부록 2> 문법 평정 목록을 등급별 JSON으로 추출한다."""

from __future__ import annotations

import json
import re
from pathlib import Path

from pypdf import PdfReader

RAW_DIR = Path("data/sources/curriculum")
OUTPUT = Path("data/reference/grammar_by_grade.json")
PAGE_FROM = 472
PAGE_TO = 486
CATEGORIES = {"조사", "선어말어미", "연결어미", "전성어미", "종결어미", "표현"}
LEVELS = {"초급", "중급", "고급", "최상급"}


def _pdf_path() -> Path:
    matches = sorted(RAW_DIR.glob("*.pdf"))
    if not matches:
        raise FileNotFoundError(f"{RAW_DIR}에 PDF가 없습니다.")
    return matches[0]


def _column_starts(lines: list[str]) -> list[int] | None:
    for line in lines:
        if all(label in line for label in ("번호", "등급", "분류", "대표형", "관련형", "의미")):
            return [line.index(label) for label in ("번호", "등급", "분류", "대표형", "관련형", "의미")]
    return None


def _field(line: str, start: int, end: int | None = None) -> str:
    return line[start:end].strip() if end is not None else line[start:].strip()


def _parse_page(text: str) -> list[dict]:
    lines = text.splitlines()
    starts = _column_starts(lines)
    if not starts:
        return []
    number_at, grade_at, category_at, form_header, related_header, meaning_header = starts
    # 헤더는 열 중앙에 있고 실제 값은 왼쪽 정렬되므로 인접 헤더의 중간을 경계로 쓴다.
    form_at = (category_at + form_header) // 2
    related_at = (form_header + related_header) // 2
    meaning_at = (related_header + meaning_header) // 2
    records: list[dict] = []
    current: dict | None = None

    for line in lines:
        row_match = re.match(
            r"^\s*(\d+)\s+([1-6])급\s+(조사|선어말어미|연결어미|전성어미|종결어미|표현)\s+",
            line,
        )
        is_row = row_match is not None

        if is_row:
            assert row_match is not None
            number_text, grade_number, category = row_match.groups()
            form = _field(line, form_at, related_at)
            related = _field(line, related_at, meaning_at)
            tail = _field(line, meaning_at)
            levels = re.findall(r"초급|중급|고급|최상급", tail)
            meaning = re.sub(r"(?:초급|중급|고급|최상급)", "", tail).strip()
            current = {
                "번호": int(number_text),
                "등급": int(grade_number),
                "분류": category,
                "대표형": re.sub(r"\d+\)$", "", form).strip(),
                "관련형": related,
                "의미": meaning,
                "국제통용단계": levels[0] if levels else "",
                "교육내용단계": levels[1] if len(levels) > 1 else "",
            }
            records.append(current)
            continue

        # 표 안에서 줄바꿈된 관련형·의미를 직전 레코드에 이어 붙인다.
        stripped_line = line.lstrip()
        if re.match(r"\d+\)", stripped_line):
            current = None
            continue
        if "국제통용" in line or "문법.표현" in line:
            continue
        if current and line.strip() and not stripped_line.startswith(("번호", "○", "<", "-")):
            left = _field(line, related_at, meaning_at) if len(line) > related_at else ""
            middle = _field(line, meaning_at) if len(line) > meaning_at else ""
            if left and not re.match(r"^\d+\)", left):
                current["관련형"] = " ".join(filter(None, [current["관련형"], left]))
            meaning_extra = re.sub(r"(?:초급|중급|고급|최상급)", "", middle).strip()
            if meaning_extra and not re.match(r"^\d+\)", meaning_extra):
                current["의미"] = " ".join(filter(None, [current["의미"], meaning_extra]))

    return records


def extract_grammar() -> dict[str, list[dict]]:
    reader = PdfReader(str(_pdf_path()))
    by_grade = {f"{grade}급": [] for grade in range(1, 7)}
    for page_number in range(PAGE_FROM, PAGE_TO + 1):
        text = reader.pages[page_number - 1].extract_text(extraction_mode="layout")
        for record in _parse_page(text):
            by_grade[f"{record['등급']}급"].append(record)

    for grade, records in by_grade.items():
        deduped = {record["번호"]: record for record in records}
        ordered = [deduped[number] for number in sorted(deduped)]
        expected = list(range(1, len(ordered) + 1))
        actual = [record["번호"] for record in ordered]
        if actual != expected:
            raise ValueError(f"{grade} 번호가 연속적이지 않습니다: {actual}")
        by_grade[grade] = ordered

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(by_grade, ensure_ascii=False, indent=2), encoding="utf-8")
    print("문법 추출 완료:", OUTPUT)
    print({grade: len(records) for grade, records in by_grade.items()})
    return by_grade


if __name__ == "__main__":
    extract_grammar()
