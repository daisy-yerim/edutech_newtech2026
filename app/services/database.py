"""SQLite connection and schema for teacher/learner data exchange."""

from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT / "data" / "runtime" / "korean_learning.sqlite3"


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    ensure_schema(conn)
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS teachers (
        teacher_id TEXT PRIMARY KEY,
        teacher_name TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS assessments (
        task_id TEXT PRIMARY KEY,
        teacher_id TEXT NOT NULL REFERENCES teachers(teacher_id),
        grade INTEGER NOT NULL CHECK (grade BETWEEN 1 AND 6),
        topic TEXT NOT NULL DEFAULT '',
        category_id TEXT NOT NULL,
        category_label TEXT NOT NULL,
        passage TEXT NOT NULL,
        writing_public_json TEXT NOT NULL,
        writing_grading_json TEXT NOT NULL,
        audit_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        published INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS reading_items (
        task_id TEXT NOT NULL REFERENCES assessments(task_id) ON DELETE CASCADE,
        item_id TEXT NOT NULL,
        position INTEGER NOT NULL,
        question_type TEXT NOT NULL,
        question TEXT NOT NULL,
        choices_json TEXT NOT NULL,
        answer TEXT NOT NULL,
        explanation TEXT NOT NULL,
        PRIMARY KEY (task_id, item_id)
    );
    CREATE TABLE IF NOT EXISTS submissions (
        submission_id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL REFERENCES assessments(task_id),
        learner_id TEXT NOT NULL DEFAULT 'learner-demo',
        reading_answers_json TEXT NOT NULL,
        writing_answer TEXT NOT NULL,
        result_json TEXT NOT NULL,
        submitted_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_assessments_lookup
        ON assessments(grade, teacher_id, published);
    """)
    conn.commit()
