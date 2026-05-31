from __future__ import annotations

import json
import logging
import sys
import time
import asyncio
from typing import Any

from fastapi import Request

from app.agent.executor import execute_query
from app.agent.llm_assistant import build_interaction_plan, stream_summary_chunks
from app.storage.repository import update_query_run_summary

STREAM_TIMEOUT = 120

_ABORT_PAYLOAD = {
    "trace_id": None,
    "answer": "查询已取消或连接已断开。",
    "table": {"rows": 0, "columns": [], "preview": [], "csv_path": None, "parquet_path": None},
    "source": {"type": "abort"},
    "warnings": ["connection lost"],
}


def sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


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


async def _should_exit(request: Request | None) -> bool:
    if request is None:
        return False
    try:
        return bool(await request.is_disconnected())
    except Exception:
        return False


def _terminal_event(event: str, data: dict[str, Any]) -> str | None:
    try:
        return sse_event(event, data)
    except Exception as exc:
        logging.error("Failed to send terminal SSE event", exc_info=exc)
        return None


async def stream_query(query: str, page: str = "1", limit: str = "100", save: bool = True, request: Request | None = None):
    start_time = time.time()
    terminal_sent = False
    try:
        yield sse_event("ping", {"message": "connected", "stage": "connected", "progress": 3})
        if await _should_exit(request):
            return

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

        if await _should_exit(request):
            yield _terminal_event("done", _ABORT_PAYLOAD)
            return

        plan = build_interaction_plan(query)

        if await _should_exit(request):
            yield _terminal_event("done", _ABORT_PAYLOAD)
            return

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
            yield _terminal_event("done", {
                "trace_id": None,
                "answer": plan.get("clarification") or "请补充更明确的查询条件。",
                "table": {"rows": 0, "columns": [], "preview": [], "csv_path": None, "parquet_path": None},
                "source": {"type": "planner", "query": query, "task_type": "need_clarification", "llm_plan": plan},
                "warnings": [],
            })
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

        if await _should_exit(request):
            yield _terminal_event("done", _ABORT_PAYLOAD)
            return

        if time.time() - start_time > STREAM_TIMEOUT:
            yield _terminal_event("error", {"message": "查询超时，请缩小查询范围后重试。"})
            return

        result = execute_query(query=query, page=page, limit=limit, save=save, llm_plan=plan, summarize=False)
        table = result.payload.get("table") or {}
        source = result.payload.get("source") or {}

        if await _should_exit(request):
            yield _terminal_event("done", _ABORT_PAYLOAD)
            return

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

        if await _should_exit(request):
            yield _terminal_event("done", _ABORT_PAYLOAD)
            return

        summary = stream_summary_chunks(
            user_query=query,
            plan=plan,
            table=table,
            source=source,
            warnings=result.payload.get("warnings") or [],
        )
        for chunk in summary.chunks:
            if await _should_exit(request):
                yield _terminal_event("done", _ABORT_PAYLOAD)
                return
            yield sse_event("summary_delta", {"delta": chunk, "stage": "summarizing", "progress": 90})
            await asyncio.sleep(0.05)

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

        terminal_sent = True
        yield sse_event("status", {"message": "完成。", "stage": "done", "progress": 100})
        yield sse_event("done", result.payload)
    except GeneratorExit:
        if not terminal_sent:
            logging.info("Stream generator closed before terminal event (client likely disconnected)")
        raise
    except Exception as exc:
        logging.error("Stream query failed", exc_info=exc)
        print(f"[streaming error] {exc}", file=sys.stderr)
        if not terminal_sent:
            yield _terminal_event(
                "error",
                {
                    "message": "请求执行失败，请稍后重试。",
                    "answer": "请求执行失败，请稍后重试或使用普通查询接口。",
                },
            )
