from __future__ import annotations

from typing import Any

import pandas as pd

from app.tools.iwencai_client import IwencaiAPIError, query_iwencai


class Query2DataError(Exception):
    def __init__(self, message: str, response: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.response = response or {}


def QUERY2DATA(query: str, page: str = "1", limit: str = "100") -> pd.DataFrame:
    try:
        result = query_iwencai(query=query, page=page, limit=limit)
    except IwencaiAPIError as exc:
        raise Query2DataError(exc.message, {"trace_id": exc.trace_id}) from exc

    payload = result.payload
    status_code = payload.get("status_code")
    if status_code != 0:
        message = payload.get("warns") or payload.get("error") or f"query2data status_code={status_code}"
        raise Query2DataError(str(message), payload)

    datas = payload.get("datas") or []
    if not datas:
        raise Query2DataError("query2data returned no data.", payload)

    columns = []
    for row in datas:
        for key in row.keys():
            if key not in columns:
                columns.append(key)
    df = pd.DataFrame(datas, columns=columns)
    df.attrs.update(
        {
            "query": query,
            "source": "iwencai_query2data",
            "status_code": status_code,
            "row_count": payload.get("row_count", len(datas)),
            "code_count": payload.get("code_count"),
            "columns_schema": payload.get("columns") or [],
            "trace_id": result.trace_id,
            "token": payload.get("token"),
            "qtime_ms": payload.get("QTime"),
            "request_payload": result.request_payload,
            "response_payload": payload,
        }
    )
    return df
