# -*- coding: utf-8 -*-
"""
config.py — 데모 전용 설정

기존 프로젝트의 상수(모델명, Ollama URL 등)와 값은 같지만,
기존 파일을 import 하지 않기 위해 여기에 다시 선언한다.
값을 바꾸려면 이 파일만 고치면 된다.
"""

from pathlib import Path

# ── 경로 ──────────────────────────────────────────────
# app/core/에서 프로젝트 루트까지 세 단계
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

PROCESSED_DIR = PROJECT_ROOT / "data" / "reference"
VOCAB_FILE = PROCESSED_DIR / "vocab_by_grade.json"
DICTIONARY_DB = PROCESSED_DIR / "korean_dictionary.sqlite"
DEMO_OUTPUT_DIR = PROJECT_ROOT / "data" / "runtime"
UPLOAD_DIR = PROJECT_ROOT / "data" / "runtime" / "uploads"

# ── 모델 ──────────────────────────────────────────────
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "gemma4:12b"
NUM_CTX = 8192            # RTX 5060 8GB에서 안정적으로 동작하는 컨텍스트
TEMPERATURE_GEN = 0.7     # 생성용
TEMPERATURE_CHECK = 0.2   # 검증·채점용 (일관성 ↑)
REQUEST_TIMEOUT = 600

# ── 문장 예시 풀 ───────────────────────────────────────
# 컨텍스트 압축본 3장 결론: 벡터 검색 대신 라벨별 딕셔너리 + 랜덤 샘플링

# ── 검증 임계값 ────────────────────────────────────────
# 등급 밖 어휘가 이 개수를 넘으면 검증 경고 (교수자 판단용 참고치)
VOCAB_VIOLATION_WARN_THRESHOLD = 5

# ── 반려 라우팅 키 ─────────────────────────────────────
ROUTE_APPROVE = "approve"
ROUTE_REJECT_READING = "reject_reading"
ROUTE_REJECT_WRITING = "reject_writing"
