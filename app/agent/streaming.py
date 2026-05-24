from __future__ import annotations

import json
from typing import Any, Iterator

import time

from app.agent.executor import execute_query
from app.agent.llm_assistant import build_interaction_plan, stream_summary_chunks
from app.storage.repository import update_query_run_summary


def sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _plan_message(plan: dict[str, Any]) -> str:
    lines = [plan.get("plan") or "优先调用问财 query2data 获取结构化金融数据。"]
    if plan.get("intent"):
        lines.append(f"意图拆解：{plan['intent']}")
    if plan.get("query_strategy"):
        lines.append(f"取数策略：{plan['query_strategy']}")
    post_process = plan.get("post_process") or []
    if post_process:
        lines.append("本地处理：" + "；".join(str(item) for item in post_process[:3]))
    validation = plan.get("validation") or []
    if validation:
        lines.append("校验重点：" + "；".join(str(item) for item in validation[:3]))
    assumptions = plan.get("assumptions") or []
    if assumptions:
        lines.append("默认假设：" + "；".join(str(item) for item in assumptions[:3]))
    return "\n".join(lines)


def stream_query(query: str, page: str = "1", limit: str = "100", save: bool = True) -> Iterator[str]:
    try:
        yield sse_event("ping", {"message": "connected", "stage": "connected", "progress": 3})
        yield sse_event(
            "think",
            {
                "message": f"收到问题：{query}\n我会先识别标的、指标和时间范围，再决定是否需要二次分析。",
                "stage": "understand",
                "progress": 8,
                "visible": True,
            },
        )
        yield sse_event(
            "think",
            {
                "message": "正在生成取数规划，若模型响应较慢会自动降级到本地规划。",
                "stage": "planning",
                "progress": 18,
                "visible": True,
            },
        )
        plan = build_interaction_plan(query)
        yield sse_event(
            "plan",
            {
                "message": _plan_message(plan),
                "plan": plan,
                "steps": plan.get("steps") or [],
                "stage": "planned",
                "progress": 30,
                "visible": True,
            },
        )
        if plan.get("need_clarification"):
            payload = {
                "trace_id": None,
                "answer": plan.get("clarification") or "请补充更明确的查询条件。",
                "table": {"rows": 0, "columns": [], "preview": [], "csv_path": None, "parquet_path": None},
                "source": {"type": "planner", "query": query, "task_type": "need_clarification", "llm_plan": plan},
                "warnings": [],
            }
            yield sse_event("done", payload)
            return

        yield sse_event(
            "tool",
            {
                "message": "正在调用问财 query2data 获取结构化数据...",
                "source": "iwencai_query2data",
                "stage": "query2data",
                "progress": 48,
            },
        )
        result = execute_query(query=query, page=page, limit=limit, save=save, llm_plan=plan, summarize=False)
        table = result.payload.get("table") or {}
        source = result.payload.get("source") or {}
        yield sse_event(
            "tool",
            {
                "message": f"结构化数据返回：{table.get('rows', 0)} 行、{len(table.get('columns') or [])} 列。",
                "source": source.get("type") or "iwencai_query2data",
                "stage": "data_ready",
                "progress": 70,
                "table": {"rows": table.get("rows", 0), "columns": table.get("columns") or []},
            },
        )
        yield sse_event(
            "summary",
            {
                "message": "结构化数据已返回，正在生成最终总结...",
                "stage": "summarizing",
                "progress": 82,
                "hide_think": True,
            },
        )
        summary = stream_summary_chunks(
            user_query=query,
            plan=plan,
            table=table,
            source=source,
            warnings=result.payload.get("warnings") or [],
        )
        for chunk in summary.chunks:
            yield sse_event("summary_delta", {"delta": chunk, "stage": "summarizing", "progress": 90})
            time.sleep(0.05)
        result.payload["answer"] = summary.answer
        result.payload["warnings"] = summary.warnings
        result.payload["visual_summary"] = summary.visual_summary
        result.payload.setdefault("source", {})["llm_plan"] = plan
        run_id = (result.payload.get("source") or {}).get("run_id")
        if run_id:
            try:
                update_query_run_summary(run_id, summary.answer, summary.visual_summary)
            except Exception as exc:
                result.payload["warnings"] = [*result.payload.get("warnings", []), f"MySQL summary persistence failed: {exc}"]
        yield sse_event("status", {"message": "完成。", "stage": "done", "progress": 100})
        yield sse_event("done", result.payload)
    except Exception as exc:
        yield sse_event(
            "error",
            {
                "message": f"流式执行失败：{exc}",
                "answer": "请求执行失败，请稍后重试或使用普通查询接口。",
            },
        )
