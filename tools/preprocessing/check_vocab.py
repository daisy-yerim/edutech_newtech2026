# -*- coding: utf-8 -*-
"""
check_vocab.py — TODO 1 결과물(vocab_by_grade.json) 검증

등급별 개수가 원본(PDF 부록)과 맞는지, 각 항목 형식이 제대로 파싱됐는지 확인.
참고: 국제 통용 한국어 표준 교육과정 공식 어휘 수 (1급 735 ~ 6급 2,580 근사치)
"""

# %% [셀 1] 불러오기 + 등급별 개수 확인
import json
from pathlib import Path

with open("data/reference/vocab_by_grade.json", encoding="utf-8") as f:
    vocab = json.load(f)

print("등급 목록:", list(vocab.keys()))
print()
for grade, items in vocab.items():
    print(f"{grade}: {len(items)}개")

# %% [셀 2] 각 등급 앞부분 3개씩 눈으로 확인 — 품사/길잡이말이 정확히 분리됐는지
for grade, items in vocab.items():
    print(f"--- {grade} 샘플 ---")
    for item in items[:3]:
        print(" ", item)
    print()

# %% [셀 3] 이상 항목 점검 — 어휘가 비어있거나, 품사가 이상하거나, 길이가 너무 긴 것
valid_pos = {"명사", "동사", "형용사", "부사", "관형사", "대명사", "수사",
             "감탄사", "의존명사", "접사", "조사", "어미"}

for grade, items in vocab.items():
    bad = [it for it in items
           if not it.get("어휘")
           or it.get("품사", "") not in valid_pos
           or len(it.get("어휘", "")) > 15]
    if bad:
        print(f"[{grade}] 이상 의심 항목 {len(bad)}개 (앞 3개만 표시)")
        for b in bad[:3]:
            print("   ", b)

# %% [셀 4] 특정 단어가 제대로 들어있는지 직접 검색 (예: "가게"가 1급에 있는지)
def find_word(word, grade=None):
    grades_to_check = [grade] if grade else vocab.keys()
    for g in grades_to_check:
        for item in vocab.get(g, []):
            if item.get("어휘") == word:
                print(f"찾음: {g} - {item}")
                return
    print(f"'{word}' 못 찾음")

find_word("가게", "1급")
find_word("가꾸다", "3급")
