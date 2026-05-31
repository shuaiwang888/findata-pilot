from __future__ import annotations

import json
import math
from typing import Any

import pandas as pd

from app.storage.mysql import pooled_connection

_schema_ensured = False


def _json(value: Any) -> str:
    return json.dumps(_clean_json(value), ensure_ascii=False, default=str)


def _clean_json(value: Any) -> Any:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, dict):
        return {key: _clean_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean_json(item) for item in value]
    return value


def _maybe_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _response_meta(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "QTime": payload.get("QTime"),
        "query": payload.get("query"),
        "row_count": payload.get("row_count"),
        "code_count": payload.get("code_count"),
        "chunks_info": payload.get("chunks_info"),
        "status_code": payload.get("status_code"),
        "token": payload.get("token"),
    }


def ensure_summary_columns() -> None:
    global _schema_ensured
    if _schema_ensured:
        return
    with pooled_connection() as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COLUMN_NAME
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'agent_query_runs'
                      AND COLUMN_NAME IN ('answer_text', 'visual_summary_json')
                    """
                )
                existing = {row["COLUMN_NAME"] for row in cursor.fetchall()}
                if "answer_text" not in existing:
                    cursor.execute("ALTER TABLE agent_query_runs ADD COLUMN answer_text LONGTEXT NULL AFTER response_meta_json")
                if "visual_summary_json" not in existing:
                    cursor.execute("ALTER TABLE agent_query_runs ADD COLUMN visual_summary_json JSON NULL AFTER answer_text")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    _schema_ensured = True


def save_failed_query_run(
    *,
    query: str,
    page: str,
    limit: str,
    trace_id: str | None,
    status_code: int | None,
    error_message: str,
    request_json: dict[str, Any] | None = None,
    response_meta_json: dict[str, Any] | None = None,
) -> int | None:
    with pooled_connection() as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO agent_query_runs (
                      trace_id, query_text, page, limit_value, status_code,
                      source, request_json, response_meta_json, error_message
                    ) VALUES (
                      %(trace_id)s, %(query_text)s, %(page)s, %(limit_value)s,
                      %(status_code)s, %(source)s, %(request_json)s,
                      %(response_meta_json)s, %(error_message)s
                    )
                    """,
                    {
                        "trace_id": trace_id,
                        "query_text": query,
                        "page": page,
                        "limit_value": limit,
                        "status_code": status_code,
                        "source": "iwencai_query2data",
                        "request_json": _json(request_json or {}),
                        "response_meta_json": _json(response_meta_json or {}),
                        "error_message": error_message,
                    },
                )
                run_id = int(cursor.lastrowid)
            conn.commit()
            return run_id
        except Exception:
            conn.rollback()
            raise


def list_query_runs(limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
    with pooled_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, trace_id, query_text, page, limit_value, status_code,
                       row_count, code_count, qtime_ms, token, source,
                       error_message, csv_path, parquet_path, created_at,
                       answer_text, visual_summary_json
                FROM agent_query_runs
                ORDER BY id DESC
                LIMIT %(limit)s OFFSET %(offset)s
                """,
                {"limit": limit, "offset": offset},
            )
            runs = list(cursor.fetchall())
            for run in runs:
                run["visual_summary_json"] = _maybe_json(run.get("visual_summary_json"))
            return runs


def get_query_run(run_id: int) -> dict[str, Any] | None:
    with pooled_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, trace_id, query_text, page, limit_value, status_code,
                       row_count, code_count, qtime_ms, token, source,
                       error_message, csv_path, parquet_path, created_at,
                       answer_text, visual_summary_json
                FROM agent_query_runs
                WHERE id = %(run_id)s
                """,
                {"run_id": run_id},
            )
            run = cursor.fetchone()
            if not run:
                return None
            run["visual_summary_json"] = _maybe_json(run.get("visual_summary_json"))

            cursor.execute(
                """
                SELECT column_order, column_key, index_name, fe_key, data_type,
                       unit, label, source, raw_json
                FROM agent_query_columns
                WHERE run_id = %(run_id)s
                ORDER BY column_order ASC, id ASC
                """,
                {"run_id": run_id},
            )
            columns = list(cursor.fetchall())
            for column in columns:
                column["raw_json"] = _maybe_json(column.get("raw_json"))
            run["columns"] = columns

            cursor.execute(
                """
                SELECT row_order, row_json
                FROM agent_query_rows
                WHERE run_id = %(run_id)s
                ORDER BY row_order ASC, id ASC
                """,
                {"run_id": run_id},
            )
            rows = list(cursor.fetchall())
            for row in rows:
                row["row_json"] = _maybe_json(row.get("row_json"))
            run["rows"] = rows
            return run


def clear_query_runs() -> dict[str, int]:
    with pooled_connection() as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS count FROM agent_query_runs")
                runs = int((cursor.fetchone() or {}).get("count") or 0)
                cursor.execute("SELECT COUNT(*) AS count FROM agent_query_columns")
                columns = int((cursor.fetchone() or {}).get("count") or 0)
                cursor.execute("SELECT COUNT(*) AS count FROM agent_query_rows")
                rows = int((cursor.fetchone() or {}).get("count") or 0)
                cursor.execute("DELETE FROM agent_query_rows")
                cursor.execute("DELETE FROM agent_query_columns")
                cursor.execute("DELETE FROM agent_query_runs")
            conn.commit()
            return {"runs": runs, "columns": columns, "rows": rows}
        except Exception:
            conn.rollback()
            raise


def update_query_run_summary(run_id: int | None, answer: str, visual_summary: dict[str, Any] | None) -> None:
    if not run_id:
        return
    with pooled_connection() as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE agent_query_runs
                    SET answer_text = %(answer_text)s,
                        visual_summary_json = %(visual_summary_json)s
                    WHERE id = %(run_id)s
                    """,
                    {
                        "run_id": run_id,
                        "answer_text": answer,
                        "visual_summary_json": _json(visual_summary or {}),
                    },
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def save_query_run(
    *,
    df: pd.DataFrame,
    query: str,
    page: str,
    limit: str,
    csv_path: str | None,
    parquet_path: str | None,
    error_message: str | None = None,
) -> int:
    attrs = df.attrs
    payload = attrs.get("response_payload") or {}
    columns_schema = attrs.get("columns_schema") or []
    records = df.where(pd.notnull(df), None).to_dict(orient="records")

    with pooled_connection() as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO agent_query_runs (
                      trace_id, query_text, page, limit_value, status_code, row_count,
                      code_count, qtime_ms, token, source, request_json,
                      response_meta_json, error_message, csv_path, parquet_path
                    ) VALUES (
                      %(trace_id)s, %(query_text)s, %(page)s, %(limit_value)s,
                      %(status_code)s, %(row_count)s, %(code_count)s, %(qtime_ms)s,
                      %(token)s, %(source)s, %(request_json)s, %(response_meta_json)s,
                      %(error_message)s, %(csv_path)s, %(parquet_path)s
                    )
                    """,
                    {
                        "trace_id": attrs.get("trace_id"),
                        "query_text": query,
                        "page": page,
                        "limit_value": limit,
                        "status_code": attrs.get("status_code"),
                        "row_count": attrs.get("row_count", len(records)),
                        "code_count": attrs.get("code_count"),
                        "qtime_ms": attrs.get("qtime_ms"),
                        "token": attrs.get("token"),
                        "source": attrs.get("source", "iwencai_query2data"),
                        "request_json": _json(attrs.get("request_payload") or {}),
                        "response_meta_json": _json(_response_meta(payload)),
                        "error_message": error_message,
                        "csv_path": csv_path,
                        "parquet_path": parquet_path,
                    },
                )
                run_id = int(cursor.lastrowid)

                for idx, column in enumerate(columns_schema):
                    cursor.execute(
                        """
                        INSERT INTO agent_query_columns (
                          run_id, column_order, column_key, index_name, fe_key,
                          data_type, unit, label, source, raw_json
                        ) VALUES (
                          %(run_id)s, %(column_order)s, %(column_key)s, %(index_name)s,
                          %(fe_key)s, %(data_type)s, %(unit)s, %(label)s,
                          %(source)s, %(raw_json)s
                        )
                        """,
                        {
                            "run_id": run_id,
                            "column_order": idx,
                            "column_key": column.get("key") or column.get("feKey") or "",
                            "index_name": column.get("index_name"),
                            "fe_key": column.get("feKey"),
                            "data_type": column.get("type"),
                            "unit": column.get("unit"),
                            "label": column.get("label"),
                            "source": column.get("source"),
                            "raw_json": _json(column),
                        },
                    )

                for idx, record in enumerate(records):
                    cursor.execute(
                        """
                        INSERT INTO agent_query_rows (run_id, row_order, row_json)
                        VALUES (%(run_id)s, %(row_order)s, %(row_json)s)
                        """,
                        {"run_id": run_id, "row_order": idx, "row_json": _json(record)},
                    )

            conn.commit()
            return run_id
        except Exception:
            conn.rollback()
            raise
