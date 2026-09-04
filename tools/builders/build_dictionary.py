"""등급별 어휘 JSON을 조회용 SQLite 사전으로 변환한다."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SOURCE = Path("data/reference/vocab_by_grade.json")
GRAMMAR_SOURCE = Path("data/reference/grammar_by_grade.json")
TARGET = Path("data/reference/korean_dictionary.sqlite")


def build_dictionary(source: Path = SOURCE, target: Path = TARGET) -> None:
    data = json.loads(source.read_text(encoding="utf-8"))
    grammar_data = json.loads(GRAMMAR_SOURCE.read_text(encoding="utf-8"))
    target.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(target) as conn:
        conn.executescript(
            """
            DROP TABLE IF EXISTS vocabulary;
            DROP TABLE IF EXISTS metadata;
            DROP TABLE IF EXISTS grammar;

            CREATE TABLE vocabulary (
                id INTEGER PRIMARY KEY,
                word TEXT NOT NULL,
                grade INTEGER NOT NULL CHECK (grade BETWEEN 1 AND 6),
                part_of_speech TEXT NOT NULL DEFAULT '',
                guide TEXT NOT NULL DEFAULT '',
                UNIQUE(word, grade, part_of_speech, guide)
            );

            CREATE INDEX idx_vocabulary_grade ON vocabulary(grade);
            CREATE INDEX idx_vocabulary_word ON vocabulary(word);
            CREATE INDEX idx_vocabulary_grade_pos
                ON vocabulary(grade, part_of_speech);

            CREATE TABLE grammar (
                id INTEGER PRIMARY KEY,
                sequence INTEGER NOT NULL,
                grade INTEGER NOT NULL CHECK (grade BETWEEN 1 AND 6),
                category TEXT NOT NULL,
                form TEXT NOT NULL,
                related_forms TEXT NOT NULL DEFAULT '',
                meaning TEXT NOT NULL DEFAULT '',
                curriculum_level TEXT NOT NULL DEFAULT '',
                education_level TEXT NOT NULL DEFAULT '',
                UNIQUE(grade, sequence)
            );

            CREATE INDEX idx_grammar_grade ON grammar(grade);
            CREATE INDEX idx_grammar_form ON grammar(form);
            CREATE INDEX idx_grammar_grade_category ON grammar(grade, category);

            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """
        )

        rows = []
        for grade_label, entries in data.items():
            grade = int(grade_label.removesuffix("급"))
            for entry in entries:
                rows.append((
                    str(entry.get("어휘", "")).strip(),
                    grade,
                    str(entry.get("품사", "")).strip(),
                    str(entry.get("길잡이말", "")).strip(),
                ))

        conn.executemany(
            """INSERT OR IGNORE INTO vocabulary
               (word, grade, part_of_speech, guide) VALUES (?, ?, ?, ?)""",
            (row for row in rows if row[0]),
        )
        count = conn.execute("SELECT COUNT(*) FROM vocabulary").fetchone()[0]
        grammar_rows = []
        for entries in grammar_data.values():
            for entry in entries:
                grammar_rows.append((
                    entry["번호"], entry["등급"], entry["분류"], entry["대표형"],
                    entry.get("관련형", ""), entry.get("의미", ""),
                    entry.get("국제통용단계", ""), entry.get("교육내용단계", ""),
                ))
        conn.executemany(
            """INSERT INTO grammar
               (sequence, grade, category, form, related_forms, meaning,
                curriculum_level, education_level)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            grammar_rows,
        )
        grammar_count = conn.execute("SELECT COUNT(*) FROM grammar").fetchone()[0]
        conn.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?)",
            [
                ("vocabulary_source", str(source)),
                ("grammar_source", str(GRAMMAR_SOURCE)),
                ("vocabulary_count", str(count)),
                ("grammar_count", str(grammar_count)),
                ("version", "2"),
            ],
        )

    print(f"사전 생성 완료: {target} (어휘 {count:,}개, 문법 {grammar_count:,}개)")


if __name__ == "__main__":
    build_dictionary()
