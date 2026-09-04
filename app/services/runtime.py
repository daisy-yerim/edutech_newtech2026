"""로컬 개발 실행에 필요한 Ollama 상태 확인과 시작."""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OLLAMA_URL = "http://127.0.0.1:11434/api/tags"


def ollama_is_running() -> bool:
    try:
        with urllib.request.urlopen(OLLAMA_URL, timeout=2):
            return True
    except OSError:
        return False


def ensure_ollama() -> bool:
    """실행 중인 Ollama를 재사용하고, 없으면 Windows GPU 서버를 시작한다."""
    if ollama_is_running():
        print("Ollama: 실행 중")
        return True

    executable = (
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Programs"
        / "Ollama"
        / "ollama.exe"
    )
    if not executable.exists():
        print(
            f"Ollama 실행 파일을 찾을 수 없습니다: {executable}",
            file=sys.stderr,
        )
        return False

    env = os.environ.copy()
    env.pop("OLLAMA_LLM_LIBRARY", None)
    env.pop("OLLAMA_NUM_GPU", None)
    env["CUDA_VISIBLE_DEVICES"] = "0"
    env["OLLAMA_VULKAN"] = "false"

    log_dir = ROOT / "data" / "runtime" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout = open(log_dir / "ollama-gpu.stdout.log", "a", encoding="utf-8")
    stderr = open(log_dir / "ollama-gpu.stderr.log", "a", encoding="utf-8")
    try:
        subprocess.Popen(
            [str(executable), "serve"],
            cwd=ROOT,
            env=env,
            stdout=stdout,
            stderr=stderr,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    finally:
        stdout.close()
        stderr.close()

    for _ in range(20):
        if ollama_is_running():
            print("Ollama: GPU 서버 시작 완료")
            return True
        time.sleep(0.5)

    print(
        "Ollama 시작 실패: data/runtime/logs/ollama-gpu.stderr.log를 확인하세요.",
        file=sys.stderr,
    )
    return False
