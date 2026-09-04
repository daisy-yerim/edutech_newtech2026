"""터미널에서 등급별 어휘 사전을 확인한다."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.dictionary import lookup_grammar, lookup_word, search_dictionary


def main() -> None:
    parser = argparse.ArgumentParser(description="한국어 등급별 어휘 사전 조회")
    parser.add_argument("query", help="표제어 또는 주제 문장")
    parser.add_argument("--grade", type=int, default=3, choices=range(1, 7))
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--exact", action="store_true", help="표제어 정확 조회")
    parser.add_argument("--grammar", action="store_true", help="문법 형태 조회")
    args = parser.parse_args()

    if args.grammar:
        results = lookup_grammar(args.query, args.grade)[: args.limit]
    elif args.exact:
        results = lookup_word(args.query, args.grade)
    else:
        results = search_dictionary(args.query, args.grade, args.limit)
    if not results:
        print("검색 결과가 없습니다.")
        return

    for item in results:
        if args.grammar:
            print(
                f"{item['form']} | {item['grade']}급 | {item['category']}"
                f" | 관련형: {item['related_forms']} | 의미: {item['meaning']}"
            )
        else:
            print(
                f"{item['word']} | {item['grade']}급 | {item['part_of_speech']}"
                f" | {item['guide']}"
            )


if __name__ == "__main__":
    main()
