from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from app.utils.trace import generate_trace_id


SKILL_NAME = "hithink-astock-selector"
SKILL_VERSION = "1.0.0"
DEFAULT_API_URL = "https://openapi.iwencai.com/v1/query2data"
DEFAULT_PAGE = "1"
DEFAULT_LIMIT = "100"
DEFAULT_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0


class IwencaiAPIError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response: str | None = None,
        trace_id: str | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response = response
        self.trace_id = trace_id


@dataclass
class IwencaiResponse:
    payload: dict[str, Any]
    trace_id: str
    request_payload: dict[str, Any]


def get_api_key(api_key: str | None = None) -> str:
    key = api_key or os.environ.get("IWENCAI_API_KEY", "")
    if not key:
        raise IwencaiAPIError(
            "API key is not configured. Set IWENCAI_API_KEY or pass api_key."
        )
    return key


def build_headers(api_key: str, trace_id: str, call_type: str = "normal") -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Claw-Call-Type": call_type,
        "X-Claw-Skill-Id": SKILL_NAME,
        "X-Claw-Skill-Version": SKILL_VERSION,
        "X-Claw-Plugin-Id": "none",
        "X-Claw-Plugin-Version": "none",
        "X-Claw-Trace-Id": trace_id,
    }


def query_iwencai(
    query: str,
    page: str = DEFAULT_PAGE,
    limit: str = DEFAULT_LIMIT,
    api_key: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    parser_logic: bool = False,
) -> IwencaiResponse:
    key = get_api_key(api_key)
    request_payload: dict[str, Any] = {
        "query": query,
        "page": page,
        "limit": limit,
        "is_cache": "1",
        "expand_index": "true",
    }
    if parser_logic:
        request_payload["parser_logic"] = True

    last_error: Exception | None = None
    last_trace_id: str | None = None
    for attempt in range(MAX_RETRIES):
        trace_id = generate_trace_id()
        last_trace_id = trace_id
        headers = build_headers(key, trace_id, "retry" if attempt > 0 else "normal")
        request = urllib.request.Request(
            DEFAULT_API_URL,
            data=json.dumps(request_payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                response_body = response.read().decode("utf-8")
                return IwencaiResponse(
                    payload=json.loads(response_body),
                    trace_id=trace_id,
                    request_payload=request_payload,
                )
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8") if exc.fp else ""
            if exc.code == 429 or 500 <= exc.code < 600:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BASE_DELAY * (2**attempt))
                    continue
            raise IwencaiAPIError(
                f"HTTP error {exc.code}: {exc.reason}",
                status_code=exc.code,
                response=error_body,
                trace_id=trace_id,
            ) from exc
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BASE_DELAY * (2**attempt))
                continue
            raise IwencaiAPIError(f"Network error: {exc.reason}", trace_id=trace_id) from exc
        except json.JSONDecodeError as exc:
            last_error = exc
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BASE_DELAY * (2**attempt))
                continue
            raise IwencaiAPIError(f"Response JSON parse failed: {exc}", trace_id=trace_id) from exc

    raise IwencaiAPIError(
        f"Failed after {MAX_RETRIES} retries: {last_error}",
        trace_id=last_trace_id,
    )
