from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from app.agent.analysis import analyze_dataframe
from app.agent.llm_assistant import build_interaction_plan, build_local_visual_summary, looks_actionable_financial_query, summarize_result
from app.agent.planner import plan_query
from app.storage.repository import save_failed_query_run, save_query_run, update_query_run_summary
from app.tools.query2data import QUERY2DATA, Query2DataError
from app.utils.env import load_env
from app.utils.dataframe import dataframe_preview, save_dataframe

load_env()

MAX_LIMIT = 500


@dataclass
class ExecutionResult:
    payload: dict[str, Any]
    status_code: int = 200


def execute_query(
    query: str,
    page: str = "1",
    limit: str = "100",
    save: bool = True,
    llm_plan: dict[str, Any] | None = None,
    summarize: bool = True,
) -> ExecutionResult:
    warnings: list[str] = []
    try:
        page_int = max(1, int(page))
    except (TypeError, ValueError):
        page_int = 1
        warnings.append("Invalid page value; defaulted to 1.")
    try:
        limit_int = min(max(1, int(limit)), MAX_LIMIT)
    except (TypeError, ValueError):
        limit_int = 100
        warnings.append("Invalid limit value; defaulted to 100.")
    page = str(page_int)
    limit = str(limit_int)

    plan = plan_query(query)
    llm_plan = llm_plan or build_interaction_plan(query)

    if llm_plan.get("need_clarification") and not looks_actionable_financial_query(query):
        clarification = llm_plan.get("clarification") or "请补充更明确的查询条件。"
        return ExecutionResult(
            payload={
                "trace_id": None,
                "answer": clarification,
                "table": {"rows": 0, "columns": [], "preview": [], "csv_path": None, "parquet_path": None},
                "source": {"type": "planner", "query": query, "task_type": "need_clarification", "llm_plan": llm_plan},
                "warnings": [],
            },
            status_code=400,
        )

    if llm_plan.get("need_clarification") and looks_actionable_financial_query(query):
        llm_plan = {**llm_plan, "task_type": "direct_query", "need_clarification": False, "clarification": "", "query": query}

    planned_analysis = llm_plan.get("analysis")
    if planned_analysis and plan.task_type == "direct_query":
        plan.task_type = "query_then_analyze"
        plan.analysis = str(planned_analysis)

    try:
        execution_query = str(llm_plan.get("query") or query).strip() or query
        df = QUERY2DATA(query=execution_query, page=page, limit=limit)
    except Query2DataError as exc:
        response = exc.response or {}
        try:
            save_failed_query_run(
                query=execution_query,
                page=page,
                limit=limit,
                trace_id=response.get("trace_id"),
                status_code=response.get("status_code"),
                error_message=exc.message,
                request_json=response.get("request_payload") if isinstance(response.get("request_payload"), dict) else None,
                response_meta_json=response,
            )
        except Exception:
            pass
        return ExecutionResult(
            payload={
                "trace_id": response.get("trace_id"),
                "answer": "问财 query2data 未返回可用数据。",
                "table": {"rows": 0, "columns": [], "preview": [], "csv_path": None, "parquet_path": None},
                "source": {
                    "type": "iwencai_query2data",
                    "query": query,
                    "data_query": execution_query,
                    "llm_plan": llm_plan,
                    "status_code": response.get("status_code"),
                    "row_count": response.get("row_count", 0),
                    "code_count": response.get("code_count"),
                },
                "warnings": [exc.message],
            },
            status_code=502,
        )

    if plan.task_type == "query_then_analyze":
        analyzed_df, analysis_warnings, analysis_info = analyze_dataframe(df, query=query, analysis=plan.analysis)
        warnings.extend(analysis_warnings)
        if analyzed_df is not df:
            df = analyzed_df
            df.attrs["analysis_info"] = analysis_info

    trace_id = str(df.attrs.get("trace_id"))
    output_dir = os.environ.get("DATA_AGENT_OUTPUT_DIR", "outputs/tables")
    csv_path = None
    parquet_path = None
    if save:
        csv_path, parquet_path, save_warnings = save_dataframe(df, trace_id, output_dir)
        warnings.extend(save_warnings)

    run_id = None
    if save:
        try:
            run_id = save_query_run(
                df=df,
                query=execution_query,
                page=page,
                limit=limit,
                csv_path=csv_path,
                parquet_path=parquet_path,
            )
        except Exception as exc:
            warnings.append(f"MySQL persistence failed: {exc}")

    table_payload = {
        "rows": int(len(df)),
        "columns": [str(col) for col in df.columns],
        "preview": dataframe_preview(df),
        "csv_path": csv_path,
        "parquet_path": parquet_path,
    }
    source_payload = {
        "type": "iwencai_query2data",
        "query": query,
        "data_query": execution_query,
        "task_type": plan.task_type,
        "analysis": plan.analysis,
        "llm_plan": llm_plan,
        "status_code": df.attrs.get("status_code"),
        "row_count": df.attrs.get("row_count"),
        "code_count": df.attrs.get("code_count"),
        "run_id": run_id,
    }
    if summarize:
        answer, warnings, visual_summary = summarize_result(
            user_query=query,
            plan=llm_plan,
            table=table_payload,
            source=source_payload,
            warnings=warnings,
        )
        if save and run_id:
            try:
                update_query_run_summary(run_id, answer, visual_summary)
            except Exception as exc:
                warnings.append(f"MySQL summary persistence failed: {exc}")
    else:
        answer = "结构化数据已返回，正在生成最终总结。"
        visual_summary = build_local_visual_summary(
            user_query=query,
            plan=llm_plan,
            table=table_payload,
            source=source_payload,
            warnings=warnings,
        )

    payload = {
        "trace_id": trace_id,
        "answer": answer,
        "visual_summary": visual_summary,
        "table": table_payload,
        "source": source_payload,
        "warnings": warnings,
    }
    return ExecutionResult(payload=payload)
