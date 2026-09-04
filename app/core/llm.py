"""Ollama 모델 호출과 JSON 응답 처리."""

import json
import time

import requests
from json_repair import repair_json

from app.core.config import (
    MODEL, NUM_CTX, OLLAMA_URL, REQUEST_TIMEOUT, TEMPERATURE_CHECK, TEMPERATURE_GEN,
)


def call_gemma(
    prompt: str,
    temperature: float = TEMPERATURE_GEN,
    json_mode: bool = False,
) -> str:
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "options": {
            "temperature": temperature,
            "num_ctx": NUM_CTX,
            "num_predict": 4096,
            "repeat_penalty": 1.15,
            "repeat_last_n": 256,
        },
    }
    if json_mode:
        payload["format"] = "json"
    response = requests.post(OLLAMA_URL, json=payload, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    body = response.json()
    result = body.get("response", "")
    if not result.strip():
        reason = body.get("done_reason", "unknown")
        raise RuntimeError(f"Ollama가 빈 응답을 반환했습니다. 종료 사유: {reason}")
    return result


def _parse_json_object(raw: str) -> dict:
    """코드 펜스나 앞뒤 설명이 섞인 응답에서 JSON 객체를 읽는다."""
    cleaned = raw.strip().replace("```json", "").replace("```", "").strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end < start:
        raise json.JSONDecodeError("JSON object boundary not found", cleaned, max(start, 0))
    candidate = cleaned[start:end + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        # 긴 설명 문자열의 따옴표나 괄호가 빠진 로컬 모델 응답을 복구한다.
        parsed = repair_json(cleaned[start:], return_objects=True)
    if not isinstance(parsed, dict):
        raise ValueError("모델 응답의 최상위 JSON은 객체여야 합니다.")
    return parsed


def call_gemma_json(prompt: str, temperature: float = TEMPERATURE_CHECK) -> dict:
    """완전한 JSON 객체를 받을 때까지 최대 3회 다시 요청한다."""
    last_error: Exception | None = None
    retry_prompt = prompt
    for attempt in range(1, 4):
        raw = call_gemma(retry_prompt, temperature=temperature, json_mode=True)
        try:
            return _parse_json_object(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            if attempt < 3:
                retry_prompt = (
                    prompt
                    + "\n\n[재출력 요청]\n이전 응답은 JSON 구문이 완성되지 않았습니다. "
                    "모든 문자열과 괄호를 닫고, 완전한 JSON 객체 하나만 처음부터 다시 출력하세요."
                )
                time.sleep(0.2)
    raise ValueError(
        "모델이 완전한 JSON을 반환하지 않아 3회 재시도 후 중단했습니다. "
        f"마지막 오류: {last_error}"
    ) from last_error


def health_check(timeout: int = 120) -> tuple[bool, str]:
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "prompt": "안녕",
                "stream": False,
                "options": {"num_predict": 1},
            },
            timeout=timeout,
        )
        response.raise_for_status()
        return True, f"{MODEL} 연결 정상"
    except requests.exceptions.ConnectionError:
        return False, "Ollama 서버에 연결할 수 없습니다. ollama serve 상태를 확인하세요."
    except requests.exceptions.ReadTimeout:
        return False, f"모델 응답 대기 시간이 {timeout}초를 초과했습니다."
    except Exception as exc:
        return False, f"확인 실패: {exc}"
