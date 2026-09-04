"""한국어 평가 시스템의 단일 개발 실행 진입점."""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import webbrowser

sys.dont_write_bytecode = True

import uvicorn

from app.services.runtime import ensure_ollama

HOST = "127.0.0.1"
PORT = 8000


def server_is_running() -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((HOST, PORT)) == 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="한국어 읽기·쓰기 평가 시스템 실행")
    parser.add_argument(
        "--page",
        choices=("teacher", "learner", "docs"),
        default="teacher",
        help="처음 열 화면 (기본값: teacher)",
    )
    parser.add_argument(
        "--skip-ollama",
        action="store_true",
        help="Ollama 상태 확인과 자동 시작을 건너뜀",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="브라우저를 자동으로 열지 않음",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="코드 변경 시 웹 서버 자동 재시작",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    path = f"/{args.page}"
    url = f"http://{HOST}:{PORT}{path}"

    if not args.skip_ollama and not ensure_ollama():
        return 1

    print(f"교수자: http://{HOST}:{PORT}/teacher")
    print(f"학습자: http://{HOST}:{PORT}/learner")
    print(f"API 문서: http://{HOST}:{PORT}/docs")

    if server_is_running():
        print(f"웹 서버: 이미 실행 중 ({url})")
        if not args.no_browser:
            webbrowser.open(url)
        return 0

    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run(
        "app.web.main:app",
        host=HOST,
        port=PORT,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
