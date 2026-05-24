from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from app.utils.env import load_env


load_env()

DEFAULT_BASE_URL = "https://api.minimaxi.com/v1"
DEFAULT_MODEL = "MiniMax-M2.7"


class MiniMaxAPIError(Exception):
    pass


def _model_name() -> str:
    configured = os.environ.get("MINIMAX_MODEL", DEFAULT_MODEL)
    aliases = {
        "minimax-2.7": "MiniMax-M2.7",
        "minimax-m2.7": "MiniMax-M2.7",
        "MiniMax-2.7": "MiniMax-M2.7",
    }
    return aliases.get(configured, configured)


def chat_completion(
    *,
    messages: list[dict[str, str]],
    temperature: float = 0.2,
    max_tokens: int = 1200,
    timeout: int = 60,
) -> str:
    api_key = os.environ.get("MINIMAX_API_KEY", "")
    if not api_key:
        raise MiniMaxAPIError("MINIMAX_API_KEY is not configured")

    base_url = os.environ.get("MINIMAX_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    url = f"{base_url}/chat/completions"
    payload: dict[str, Any] = {
        "model": _model_name(),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8") if exc.fp else ""
        raise MiniMaxAPIError(f"MiniMax HTTP {exc.code}: {error_body or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise MiniMaxAPIError(f"MiniMax network error: {exc.reason}") from exc

    try:
        data = json.loads(body)
        return _strip_thinking(data["choices"][0]["message"]["content"])
    except Exception as exc:
        raise MiniMaxAPIError(f"MiniMax response parse failed: {body[:500]}") from exc


def _strip_thinking(content: str) -> str:
    if "</think>" in content:
        content = content.split("</think>", 1)[1]
    return content.replace("<think>", "").strip()
