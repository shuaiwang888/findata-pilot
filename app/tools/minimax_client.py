from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from typing import Any

from app.utils.env import load_env


load_env()

DEFAULT_BASE_URL = "https://api.minimaxi.com/v1"
DEFAULT_MODEL = "MiniMax-M2.7"

# When MINIMAX_BASE_URL ends with "/anthropic" the client switches to the
# Anthropic-compatible Messages API. Otherwise the OpenAI-compatible
# /chat/completions protocol is used.
_ANTHROPIC_PATH_HINTS = ("/anthropic",)


class MiniMaxAPIError(Exception):
    pass


def _model_name() -> str:
    configured = os.environ.get("MINIMAX_MODEL", DEFAULT_MODEL)
    aliases = {
        "minimax-2.7": "MiniMax-M2.7",
        "minimax-m2.7": "MiniMax-M2.7",
        "minimax-2.7": "MiniMax-M2.7",
        "minimax-3": "MiniMax-M3",
        "minimax-m3": "MiniMax-M3",
        "minimax-3.0": "MiniMax-M3",
    }
    return aliases.get(configured, configured)


def _is_anthropic_endpoint(base_url: str) -> bool:
    lowered = base_url.lower()
    return any(hint in lowered for hint in _ANTHROPIC_PATH_HINTS)


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
    model = _model_name()

    if _is_anthropic_endpoint(base_url):
        return _call_anthropic(
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
    return _call_openai(
        base_url=base_url,
        api_key=api_key,
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )


def _call_openai(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
    timeout: int,
) -> str:
    url = f"{base_url}/chat/completions"
    payload: dict[str, Any] = {
        "model": model,
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
    except (TimeoutError, socket.timeout) as exc:
        raise MiniMaxAPIError(f"MiniMax timeout after {timeout}s: {exc}") from exc

    try:
        data = json.loads(body)
        return _strip_thinking(data["choices"][0]["message"]["content"])
    except Exception as exc:
        raise MiniMaxAPIError(f"MiniMax response parse failed: {body[:500]}") from exc


def _call_anthropic(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
    timeout: int,
) -> str:
    # Anthropic Messages API. Two URL patterns are supported:
    #   1. MINIMAX_BASE_URL is a host root (e.g. https://api.minimaxi.com/anthropic)
    #      → POST {base_url}/v1/messages
    #   2. MINIMAX_BASE_URL already points at the API root (e.g. https://api.minimaxi.com/anthropic/v1)
    #      → POST {base_url}/messages
    system_text, anthropic_messages = _convert_messages(messages)
    if base_url.lower().endswith("/v1"):
        url = f"{base_url}/messages"
    else:
        url = f"{base_url}/v1/messages"
    payload: dict[str, Any] = {
        "model": model,
        "messages": anthropic_messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if system_text:
        payload["system"] = system_text

    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
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
    except (TimeoutError, socket.timeout) as exc:
        raise MiniMaxAPIError(f"MiniMax timeout after {timeout}s: {exc}") from exc

    try:
        data = json.loads(body)
        content = data.get("content") or []
        text_chunks = [part.get("text", "") for part in content if part.get("type") in ("text", None)]
        combined = "".join(text_chunks) or data.get("completion", "")
        return _strip_thinking(combined)
    except Exception as exc:
        raise MiniMaxAPIError(f"MiniMax response parse failed: {body[:500]}") from exc


def _convert_messages(messages: list[dict[str, str]]) -> tuple[str, list[dict[str, Any]]]:
    """Split OpenAI-style messages into Anthropic system + messages."""
    system_parts: list[str] = []
    converted: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            system_parts.append(content)
            continue
        converted.append({"role": role if role in ("user", "assistant") else "user", "content": content})
    return "\n\n".join(system_parts), converted


def _strip_thinking(content: str) -> str:
    if not content:
        return ""
    if "</think>" in content:
        content = content.split("</think>", 1)[1]
    return content.replace("<think>", "").strip()
