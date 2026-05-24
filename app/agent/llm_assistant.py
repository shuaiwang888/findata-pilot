from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.tools.minimax_client import MiniMaxAPIError, chat_completion


SYSTEM_PROMPT = """你是一个顶尖的数据分析师，来自 FinDataPilot。
你的核心任务是深刻理解用户的金融数据需求，并基于系统已经调用 QUERY2DATA 获得的结构化结果，给出可信、可追溯、适合可视化展示的最终总结。

当前运行环境说明：
1. 后端服务负责调用内部可靠数据库 QUERY2DATA，并把结果整理为 table/source/plan/warnings 传给你。
2. 你不能真实执行 Python，也不能安装库；不要声称自己调用了代码解释器、函数命名空间或外部工具。
3. QUERY2DATA 是结构化数据接口，不负责完整业务推理；你需要完成意图解释、口径说明、结果取舍和风险提示。
4. 前端会把 visual_summary 解析成统一结果框，因此你的回答要服务于“查询结论、结果要点、口径与处理、查询结果、数据来源、注意事项”的展示。

工作规则：
1. 优先相信 QUERY2DATA 返回的非空结构化数据；如果无数据或告警，要明确说明，不编造替代数据。
2. 一般金融问句优先按股票类问题理解；用户明确提到 A股、港股、美股、基金、指数、ETF、可转债、期货等时按用户口径处理。
3. 对直接取数结果，说明关键字段、样本数量、时间口径和数据来源。
4. 对经过二次加工的数据，说明加工逻辑，例如筛选、合并、新增列、均线、收益率、波动率、最大回撤等。
5. 只基于 table.preview/table.columns/source/plan/warnings 中存在的信息总结；不要编造 preview 中不存在的具体数值。
6. 日期必须严格依据字段名或原始数据，不要把 20260521 改写成 2025 年或其他年份；不确定日期含义时保留原始字段名。
7. 不提供投资建议，不使用“买入/卖出/保证收益”等表述。
8. 回复要适合出现在 FinDataPilot 对话工作台中，不要输出代码块，不要输出 JSON，不要输出 <apply> 标签。
9. 默认使用用户提问语言；当前产品默认中文。
"""


PLAN_PROMPT = """你是 FinDataPilot 的规划器，负责把用户的金融数据问题转成可执行规划。
必须只输出 JSON 对象，不要输出 Markdown、代码块或解释性前后缀。

JSON 字段：
- task_type: direct_query | query_then_analyze | need_clarification
- query: 可以直接交给 QUERY2DATA 的中文取数问句；QUERY2DATA 只是结构化取数接口，不会替你完成完整推理
- plan: 2-4 句自然语言规划，先说明用户真实意图，再说明取数、加工和校验策略
- intent: 用户真实业务目标，不能只复述原问句
- entities: 标的、市场、行业、主题、账户或指数等对象数组；无法识别时为空数组
- metrics: 需要返回或计算的指标数组
- time_range: 用户要求的时间范围；无明确时间时写“最新可得”
- filters: 筛选、排序、分组、TopN、阈值等条件数组
- query_strategy: 如何把业务问题改写成一次或多次 QUERY2DATA 结构化取数
- post_process: 取数后需要在本地完成的计算、合并、排序、校验或解释动作数组
- validation: 需要检查的数据质量点数组，例如行数、关键字段、日期口径、空值、单位
- steps: 4-6 个短步骤，每个步骤是用户可见的执行动作，必须体现“拆解问题 -> 结构化取数 -> 本地处理 -> 校验 -> 总结”
- assumptions: 0-3 个默认假设，例如未说明市场时默认股票、未说明日期时按最新可得数据
- data_requirements: 对象，包含 entities、metrics、time_range、filters、sort、limit
- analysis: moving_average | return | volatility | max_drawdown | null
- need_clarification: 布尔值
- clarification: need_clarification=true 时给用户的一句话追问，否则为空字符串

规划原则：
1. 必须先拆解用户真实目标、标的类型、指标、时间范围、筛选/排序/TopN 条件，再决定取数问句。
2. 内部可靠数据库 QUERY2DATA 优先；query 必须是中文自然语言取数问句，并尽量把数据库可直接完成的筛选、排序和简单计算写进 query。
3. QUERY2DATA 只负责取回结构化数据；跨表合并、衍生指标、异常校验、口径说明、可视化解释要写入 post_process/validation。
4. 不要设计“大范围全量取数后本地暴力筛选”的冗余流程；复杂条件能用一句 QUERY2DATA 表达时，优先直接表达。
5. 只有均线、收益率、波动率、最大回撤等明确需要本地二次计算时，才使用 query_then_analyze。
6. 用户未明确标的类型时，默认按股票理解；未明确时间时，默认最新可得，除非这会改变问题含义。
7. 如果缺少完成任务的关键标的、指标或时间范围，并且无法用默认值合理补齐，才追问。
8. 不编造任何具体数据值，不假设工具已经返回结果。
9. 规划中要体现最终会产出非空结构化结果；如果预计可能无数据，在 validation 中要求检查并说明。

QUERY2DATA 错误处理口径：
- status_code 为 -2326、-2126、-1325：通常表示统计量过大或超时，建议缩短时间范围、减少指标或收窄标的范围。
- status_code 为 -2331、-1330、-2309：通常表示数据库查询超时，可建议重试。
- status_code 为 -2322、-2321、-1321：通常表示指标不存在，需要调整指标表达。
- status_code 为 -225：通常表示指标在当前周期表不存在，需调整周期或指标口径。
"""


@dataclass
class StreamSummary:
    answer: str
    chunks: list[str]
    warnings: list[str]
    visual_summary: dict[str, Any]


def build_interaction_plan(user_query: str) -> dict[str, Any]:
    fallback = _local_plan(user_query)
    try:
        content = chat_completion(
            messages=[
                {"role": "system", "content": PLAN_PROMPT},
                {
                    "role": "user",
                    "content": f"用户问题：{user_query}",
                },
            ],
            temperature=0.1,
            max_tokens=900,
            timeout=12,
        )
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            parsed = json.loads(content[start : end + 1])
            return _normalize_plan({**fallback, **parsed}, user_query)
    except Exception:
        return fallback
    return fallback


def _local_plan(user_query: str) -> dict[str, Any]:
    normalized = user_query.strip().lower()
    if not normalized:
        return {
            "task_type": "need_clarification",
            "query": user_query,
            "plan": "需要先补充查询问题，再开始取数。",
            "intent": "等待用户提供金融数据查询目标。",
            "entities": [],
            "metrics": [],
            "time_range": "",
            "filters": [],
            "query_strategy": "暂不调用 QUERY2DATA。",
            "post_process": [],
            "validation": [],
            "steps": ["等待用户补充金融数据查询问题"],
            "assumptions": [],
            "data_requirements": {
                "entities": [],
                "metrics": [],
                "time_range": "",
                "filters": [],
                "sort": "",
                "limit": "",
            },
            "analysis": None,
            "need_clarification": True,
            "clarification": "请输入需要查询的金融取数问题。",
        }

    analysis = _detect_analysis(normalized)
    task_type = "query_then_analyze" if analysis else "direct_query"
    metrics = _guess_metrics(normalized)
    time_range = _guess_time_range(normalized)
    filters = _guess_filters(user_query)
    post_process = ["整理返回字段并保留关键结果"]
    if analysis:
        post_process.insert(0, f"基于结构化数据计算{_analysis_label(analysis)}")
    validation = ["检查返回行数是否大于 0", "检查关键指标字段是否存在", "核对日期字段和用户时间要求是否一致"]
    steps = [
        "拆解用户意图、标的、指标、时间范围和筛选条件",
        "将可由数据库完成的条件改写为 QUERY2DATA 结构化取数问句",
        "调用问财 query2data 获取结构化数据",
    ]
    if analysis:
        steps.append(f"对返回数据执行{_analysis_label(analysis)}计算")
    steps.extend(["校验返回行数、关键字段、日期口径和空值", "基于结构化结果生成业务化总结"])

    assumptions: list[str] = []
    if not any(word in normalized for word in ("a股", "港股", "美股", "基金", "指数", "期货", "可转债", "etf")):
        assumptions.append("未明确标的市场时，优先按股票类金融数据理解。")
    if not any(word in normalized for word in ("今天", "昨日", "昨天", "最新", "近", "今年", "去年", "20")):
        assumptions.append("未明确时间时，优先查询最新可得数据。")

    return {
        "task_type": task_type,
        "query": user_query,
        "plan": "先拆解用户问题中的业务意图、标的、指标、时间范围和筛选条件；再把数据库可直接完成的部分组织为 QUERY2DATA 取数问句。"
        + (" 返回后在本地执行必要的二次计算、字段校验和结果总结。" if analysis else " 返回后进行字段校验、口径说明和业务总结。"),
        "intent": f"回答用户关于「{user_query}」的金融数据问题。",
        "entities": [],
        "metrics": metrics,
        "time_range": time_range,
        "filters": filters,
        "query_strategy": "优先把标的、指标、时间、筛选和排序条件交给 QUERY2DATA 返回结构化数据；本地只处理接口无法直接完成的计算和解释。",
        "post_process": post_process,
        "validation": validation,
        "steps": steps,
        "assumptions": assumptions,
        "data_requirements": {
            "entities": [],
            "metrics": metrics,
            "time_range": time_range,
            "filters": filters,
            "sort": "按用户问题要求排序" if any(word in normalized for word in ("前", "后", "最高", "最低", "最大", "最小", "排名")) else "",
            "limit": "按用户问题要求截取" if any(word in normalized for word in ("前", "top", "只", "个")) else "",
        },
        "analysis": analysis,
        "need_clarification": False,
        "clarification": "",
    }


def _normalize_plan(plan: dict[str, Any], user_query: str) -> dict[str, Any]:
    fallback = _local_plan(user_query)
    normalized = {**fallback, **plan}
    if normalized.get("task_type") not in {"direct_query", "query_then_analyze", "need_clarification"}:
        normalized["task_type"] = "direct_query"
    if not isinstance(normalized.get("query"), str) or not normalized["query"].strip():
        normalized["query"] = user_query
    if not isinstance(normalized.get("plan"), str) or not normalized["plan"].strip():
        normalized["plan"] = _local_plan(user_query)["plan"]
    if not isinstance(normalized.get("steps"), list):
        normalized["steps"] = fallback["steps"]
    normalized["steps"] = [str(step).strip() for step in normalized["steps"] if str(step).strip()][:6]
    if not normalized["steps"]:
        normalized["steps"] = fallback["steps"]
    if not isinstance(normalized.get("assumptions"), list):
        normalized["assumptions"] = []
    normalized["assumptions"] = [str(item).strip() for item in normalized["assumptions"] if str(item).strip()][:3]
    for key in ("entities", "metrics", "filters", "post_process", "validation"):
        if not isinstance(normalized.get(key), list):
            normalized[key] = fallback.get(key, [])
        normalized[key] = [str(item).strip() for item in normalized[key] if str(item).strip()]
    for key in ("intent", "time_range", "query_strategy"):
        if not isinstance(normalized.get(key), str) or not normalized[key].strip():
            normalized[key] = fallback.get(key, "")
    if not isinstance(normalized.get("data_requirements"), dict):
        normalized["data_requirements"] = fallback["data_requirements"]
    normalized["analysis"] = normalized.get("analysis") or _detect_analysis(user_query.lower())
    normalized["need_clarification"] = bool(normalized.get("need_clarification"))
    if normalized["task_type"] == "need_clarification":
        normalized["need_clarification"] = True
    if normalized["need_clarification"] and _looks_actionable_query(user_query):
        normalized["task_type"] = fallback["task_type"]
        normalized["need_clarification"] = False
        normalized["clarification"] = ""
        normalized["query"] = str(normalized.get("query") or user_query).strip() or user_query
    if not isinstance(normalized.get("clarification"), str):
        normalized["clarification"] = ""
    return normalized


def _looks_actionable_query(query: str) -> bool:
    normalized = query.strip().lower()
    if not normalized:
        return False
    object_keywords = (
        "自选股",
        "持仓",
        "股票",
        "基金",
        "指数",
        "etf",
        "a股",
        "港股",
        "美股",
        "板块",
        "行业",
        "概念",
        "市场",
    )
    metric_keywords = (
        "涨跌幅",
        "涨幅",
        "跌幅",
        "行情",
        "收盘价",
        "最新价",
        "成交量",
        "成交额",
        "市值",
        "pe",
        "净利润",
        "roe",
        "表现",
        "情况",
        "排名",
        "走势",
    )
    return any(word in normalized for word in object_keywords) and any(word in normalized for word in metric_keywords)


def _guess_metrics(normalized_query: str) -> list[str]:
    metrics: list[str] = []
    candidates = (
        "收盘价",
        "最新价",
        "成交量",
        "成交额",
        "涨跌幅",
        "市值",
        "pe",
        "市盈率",
        "净利润",
        "roe",
        "营收",
        "股息率",
        "换手率",
        "均线",
        "波动率",
        "最大回撤",
    )
    for item in candidates:
        if item in normalized_query:
            metrics.append(item.upper() if item == "pe" else item)
    return metrics


def _guess_time_range(normalized_query: str) -> str:
    for marker in ("最新", "今天", "昨日", "昨天", "今年", "去年", "近"):
        if marker in normalized_query:
            return "按用户问题中的时间表达取数"
    return "最新可得"


def _guess_filters(user_query: str) -> list[str]:
    filters: list[str] = []
    lowered = user_query.lower()
    for marker in ("前", "top", "大于", "小于", "超过", "以内", "连续", "排名", "最高", "最低"):
        if marker in lowered:
            filters.append(f"包含筛选或排序条件：{user_query}")
            break
    return filters


def _detect_analysis(normalized_query: str) -> str | None:
    if any(keyword in normalized_query for keyword in ("均线", "移动平均", "ma")):
        return "moving_average"
    if any(keyword in normalized_query for keyword in ("收益率", "涨跌幅", "涨幅", "跌幅")):
        return "return"
    if any(keyword in normalized_query for keyword in ("波动率", "标准差")):
        return "volatility"
    if any(keyword in normalized_query for keyword in ("最大回撤", "回撤")):
        return "max_drawdown"
    return None


def _analysis_label(analysis: str) -> str:
    labels = {
        "moving_average": "均线",
        "return": "收益率",
        "volatility": "波动率",
        "max_drawdown": "最大回撤",
    }
    return labels.get(analysis, analysis)


def summarize_result(
    *,
    user_query: str,
    plan: dict[str, Any],
    table: dict[str, Any],
    source: dict[str, Any],
    warnings: list[str],
) -> tuple[str, list[str], dict[str, Any]]:
    if not table.get("rows"):
        visual = _local_visual_summary(user_query=user_query, plan=plan, table=table, source=source, warnings=warnings)
        return "问财 query2data 未返回可用数据。", warnings, visual

    preview = table.get("preview") or []
    compact_payload = {
        "user_query": user_query,
        "plan": plan,
        "source": source,
        "table": {
            "rows": table.get("rows"),
            "columns": table.get("columns"),
            "preview": preview[:5],
        },
        "warnings": warnings,
    }
    try:
        answer = chat_completion(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "下面是金融数据查询任务、执行规划和 QUERY2DATA 返回的结构化结果。"
                        "请生成对话工作台里的最终回答，要求：\n"
                        "1. 使用中文 Markdown，但不要使用代码块，不要输出 JSON，不要输出 <apply> 标签。\n"
                        "2. 结构必须依次包含这些小节：## 查询结论、## 结果要点、## 口径与处理、## 数据来源、## 注意事项。\n"
                        "3. 查询结论：一句话回答用户问题是否已完成；若只是返回结构化数据，要明确说是基于返回字段的结果；"
                        "如果 table.rows 为 0，必须明确未返回非空数据。\n"
                        "4. 结果要点：从 preview 中提炼 2-5 条高价值信息；优先引用具体股票/代码/日期/指标值；"
                        "有排序、TopN、阈值、日期、单位时必须点明；不要把表头或总行数当成主要要点。\n"
                        "5. 口径与处理：说明实际取数问句、指标口径、时间范围、筛选/排序条件、是否做了二次计算或本地处理；"
                        "如果没有二次处理，也要说明当前只是结构化取数结果。\n"
                        "6. 数据来源：说明来源为 QUERY2DATA 结构化数据接口，并写出返回行数、列数和可用文件路径（如果 source/table 中存在）。\n"
                        "7. 注意事项：只写真实限制，例如预览只展示部分行、字段单位需以列名/接口为准、无数据或告警；没有明显限制则写“暂无额外告警”。\n"
                        "8. 不编造 preview 中不存在的具体数值，不把日期字段改写成其他年份，不做投资建议。\n"
                        "9. 保持简洁，避免重复输出完整表格，因为前端会单独展示结构化表格和图表。\n"
                        + json.dumps(compact_payload, ensure_ascii=False)
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=1400,
            timeout=14,
        )
        visual = build_visual_summary(
            user_query=user_query,
            plan=plan,
            table=table,
            source=source,
            warnings=warnings,
            answer=answer,
        )
        return answer.strip(), warnings, visual
    except MiniMaxAPIError as exc:
        next_warnings = [*warnings, f"MiniMax summary failed: {exc}"]
        fallback = _local_summary(user_query=user_query, table=table, source={**source, "warnings": next_warnings})
        visual = _local_visual_summary(
            user_query=user_query,
            plan=plan,
            table=table,
            source=source,
            warnings=next_warnings,
        )
        return fallback, next_warnings, visual


def build_visual_summary(
    *,
    user_query: str,
    plan: dict[str, Any],
    table: dict[str, Any],
    source: dict[str, Any],
    warnings: list[str],
    answer: str = "",
) -> dict[str, Any]:
    local = _local_visual_summary(user_query=user_query, plan=plan, table=table, source=source, warnings=warnings)
    preview = table.get("preview") or []
    compact_payload = {
        "user_query": user_query,
        "answer": answer[:2000],
        "plan": plan,
        "source": source,
        "table": {
            "rows": table.get("rows"),
            "columns": table.get("columns"),
            "preview": preview[:50],
        },
        "warnings": warnings,
        "required_schema": {
            "title": "短标题",
            "query_type": "stock_selection | data_query | ranking | analysis | unknown",
            "headline": "一句话结论",
            "stats": [{"label": "具体字段", "value": "具体值", "hint": "可选说明"}],
            "insights": ["2-5条基于结果的洞察"],
            "result_columns": ["用于可视化表格的列名，最多8列"],
            "result_rows": [{"列名": "值"}],
            "method": ["取数和处理步骤"],
            "warnings": ["注意事项"],
        },
    }
    try:
        content = chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是 FinDataPilot 的金融数据结果可视化助手。必须只输出 JSON 对象，不要 Markdown、不要代码块。"
                        "你要把 QUERY2DATA 返回的非空结构化结果整理成统一报告和可视化面板所需结构。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "请基于 QUERY2DATA 结构化结果生成 visual_summary。要求："
                        "1. result_rows 必须来自 table.preview，不得编造具体数值；"
                        "2. result_columns 选择最能代表选股/查询结果的列，最多8列；"
                        "选股/股票类结果优先选择股票代码、股票简称、日期、涨跌幅、最新价/收盘价、成交额、成交量、行业/板块等可视化友好字段；"
                        "3. headline 必须是一句话查询结论，可直接放入“查询结论”；"
                        "4. stats 必须展示结构化结果里的具体数据值，例如首条记录的股票简称、涨跌幅、收盘价、日期等；"
                        "不要把总行数、字段数、表头名当作主要 stats；"
                        "5. insights 用业务语言解释结果，适合放入“结果要点”，但不能给投资建议；"
                        "6. method 写清取数、筛选、排序、二次处理和校验口径，适合放入“口径与处理”；"
                        "7. warnings 写真实限制，没有则为“暂无额外告警”；"
                        "8. 如果 table.rows 为 0，不得构造 result_rows，必须在 headline/warnings 说明无非空数据。\n"
                        + json.dumps(compact_payload, ensure_ascii=False)
                    ),
                },
            ],
            temperature=0.1,
            max_tokens=1400,
            timeout=12,
        )
        parsed = _extract_json_object(content)
        if parsed:
            return _normalize_visual_summary(parsed, local)
    except Exception:
        return local
    return local


def build_local_visual_summary(
    *,
    user_query: str,
    plan: dict[str, Any],
    table: dict[str, Any],
    source: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    return _local_visual_summary(
        user_query=user_query,
        plan=plan,
        table=table,
        source=source,
        warnings=warnings,
    )


def stream_summary_chunks(
    *,
    user_query: str,
    plan: dict[str, Any],
    table: dict[str, Any],
    source: dict[str, Any],
    warnings: list[str],
) -> StreamSummary:
    try:
        answer, final_warnings, visual_summary = summarize_result(
            user_query=user_query,
            plan=plan,
            table=table,
            source=source,
            warnings=warnings,
        )
    except Exception as exc:
        final_warnings = [*warnings, f"MiniMax summary failed: {exc}"]
        answer = _local_summary(user_query=user_query, table=table, source=source)
        visual_summary = _local_visual_summary(
            user_query=user_query,
            plan=plan,
            table=table,
            source=source,
            warnings=final_warnings,
        )
    chunks = _split_answer(answer)
    return StreamSummary(answer=answer, chunks=chunks, warnings=final_warnings, visual_summary=visual_summary)


def _local_summary(*, user_query: str, table: dict[str, Any], source: dict[str, Any]) -> str:
    warnings = source.get("warnings") or []
    return "\n\n".join(
        part
        for part in [
            f"**查询结论**\n{_compact_intro(user_query, table, source)}",
            f"**结果要点**\n{_compact_columns(table) or '已返回结构化结果，可在右侧预览查看明细。'}",
            f"**口径与处理**\n{_compact_processing(source)}",
            f"**数据来源**\n{_compact_source(source)}",
            f"**注意事项**\n{'; '.join(warnings) if warnings else '暂无额外告警。'}",
        ]
        if part
    )


def _local_visual_summary(
    *,
    user_query: str,
    plan: dict[str, Any],
    table: dict[str, Any],
    source: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    rows = table.get("preview") or []
    columns = [str(col) for col in (table.get("columns") or [])]
    selected_columns = _select_visual_columns(columns, rows)
    query_type = _query_type(plan, user_query)
    visual_rows = []
    for row in rows[:50]:
        visual_rows.append({col: row.get(col) for col in selected_columns if col in row})

    stats = _specific_value_stats(rows, selected_columns)
    time_range = plan.get("time_range")
    if time_range:
        stats.append({"label": "时间范围", "value": str(time_range), "hint": "来自问题拆解或默认口径"})
    if plan.get("metrics"):
        stats.append({"label": "核心指标", "value": "、".join(str(item) for item in plan.get("metrics", [])[:3]), "hint": ""})

    insights = []
    if table.get("rows"):
        insights.append(f"下方表格展示 query2data 返回的具体结构化明细，当前可查看 {len(visual_rows)} 条预览记录。")
    if selected_columns:
        insights.append("可视化表格优先展示：" + "、".join(selected_columns[:6]) + "。")
    if plan.get("post_process"):
        insights.append("后续处理关注：" + "；".join(str(item) for item in plan.get("post_process", [])[:2]) + "。")

    return {
        "title": _visual_title(query_type),
        "query_type": query_type,
        "headline": _compact_intro(user_query, table, source),
        "stats": stats[:6],
        "insights": insights[:5],
        "result_columns": selected_columns,
        "result_rows": visual_rows,
        "method": [str(item) for item in (plan.get("steps") or [])[:5]],
        "warnings": warnings or ["暂无额外告警。"],
    }


def _extract_json_object(content: str) -> dict[str, Any] | None:
    start = content.find("{")
    end = content.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(content[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _normalize_visual_summary(parsed: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    visual = {**fallback, **parsed}
    for key in ("title", "query_type", "headline"):
        if not isinstance(visual.get(key), str) or not visual[key].strip():
            visual[key] = fallback.get(key, "")
    for key in ("stats", "insights", "result_columns", "result_rows", "method", "warnings"):
        if not isinstance(visual.get(key), list):
            visual[key] = fallback.get(key, [])
    visual["stats"] = [_normalize_stat(item) for item in visual["stats"][:6] if item]
    visual["insights"] = [str(item) for item in visual["insights"] if str(item).strip()][:6]
    visual["result_columns"] = [str(item) for item in visual["result_columns"] if str(item).strip()][:8]
    normalized_rows = []
    for row in visual["result_rows"][:50]:
        if isinstance(row, dict):
            normalized_rows.append({str(key): value for key, value in row.items()})
    visual["result_rows"] = normalized_rows
    visual["method"] = [str(item) for item in visual["method"] if str(item).strip()][:6]
    visual["warnings"] = [str(item) for item in visual["warnings"] if str(item).strip()] or ["暂无额外告警。"]
    return visual


def _specific_value_stats(rows: list[dict[str, Any]], selected_columns: list[str]) -> list[dict[str, str]]:
    if not rows or not selected_columns:
        return []
    first = rows[0]
    stats: list[dict[str, str]] = []
    for column in selected_columns[:6]:
        value = first.get(column)
        if value is None or value == "":
            continue
        stats.append({"label": column, "value": str(value), "hint": "首条结果"})
    return stats


def _normalize_stat(item: Any) -> dict[str, str]:
    if isinstance(item, dict):
        return {
            "label": str(item.get("label") or "指标"),
            "value": str(item.get("value") or ""),
            "hint": str(item.get("hint") or ""),
        }
    return {"label": "指标", "value": str(item), "hint": ""}


def _select_visual_columns(columns: list[str], rows: list[dict[str, Any]]) -> list[str]:
    if not columns:
        return []
    priority_keywords = (
        "股票代码",
        "股票简称",
        "证券代码",
        "证券简称",
        "代码",
        "简称",
        "名称",
        "日期",
        "时间",
        "收盘价",
        "最新价",
        "涨跌幅",
        "成交额",
        "成交量",
        "市值",
        "市盈率",
        "PE",
        "净利润",
        "ROE",
        "排名",
    )
    selected: list[str] = []
    for keyword in priority_keywords:
        for column in columns:
            if column not in selected and keyword.lower() in column.lower():
                selected.append(column)
            if len(selected) >= 8:
                return selected
    for column in columns:
        if column not in selected:
            selected.append(column)
        if len(selected) >= 8:
            break
    if rows and not selected:
        selected = list(rows[0].keys())[:8]
    return selected


def _query_type(plan: dict[str, Any], user_query: str) -> str:
    text = f"{user_query} {plan.get('intent', '')} {plan.get('query', '')}".lower()
    if any(word in text for word in ("选股", "筛选", "找出", "哪些", "前十大", "前10", "top")):
        return "stock_selection"
    if any(word in text for word in ("排名", "前", "最高", "最低", "top")):
        return "ranking"
    if plan.get("analysis"):
        return "analysis"
    if text.strip():
        return "data_query"
    return "unknown"


def _visual_title(query_type: str) -> str:
    titles = {
        "stock_selection": "选股结果",
        "ranking": "排行结果",
        "analysis": "分析结果",
        "data_query": "查询结果",
        "unknown": "结构化结果",
    }
    return titles.get(query_type, "结构化结果")


def _split_answer(answer: str) -> list[str]:
    normalized = answer.replace("\r\n", "\n").strip()
    if not normalized:
        return []
    parts = [part.strip() for part in normalized.split("\n\n") if part.strip()]
    if len(parts) > 1:
        return parts
    sentences: list[str] = []
    current = ""
    for char in normalized:
        current += char
        if char in "。！？!?":
            sentences.append(current.strip())
            current = ""
    if current.strip():
        sentences.append(current.strip())
    return sentences or [normalized]


def _compact_intro(user_query: str, table: dict[str, Any], source: dict[str, Any]) -> str:
    rows = table.get("rows") or 0
    if rows:
        return f"问题「{user_query}」已返回 {rows} 行结构化数据。"
    return f"问题「{user_query}」未返回可用数据。"


def _compact_columns(table: dict[str, Any]) -> str:
    columns = table.get("columns") or []
    preview = table.get("preview") or []
    if not columns or not preview:
        return ""
    first = preview[0]
    fields = []
    for key in columns[:4]:
        if key in first:
            fields.append(f"{key}={first.get(key)}")
    if not fields:
        return ""
    return "关键字段：" + "，".join(fields) + "。"


def _compact_source(source: dict[str, Any]) -> str:
    src = source.get("type") or "iwencai_query2data"
    query = source.get("data_query") or source.get("query") or ""
    return f"数据来源：{src} 结构化数据接口；实际取数问句为「{query}」。"


def _compact_processing(source: dict[str, Any]) -> str:
    plan = source.get("llm_plan") or {}
    post_process = plan.get("post_process") or []
    validation = plan.get("validation") or []
    parts = []
    if post_process:
        parts.append("处理动作：" + "；".join(str(item) for item in post_process[:3]))
    else:
        parts.append("当前结果主要来自结构化取数，未执行额外二次加工。")
    if validation:
        parts.append("校验重点：" + "；".join(str(item) for item in validation[:3]))
    return " ".join(parts)
