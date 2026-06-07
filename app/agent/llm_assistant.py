from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.tools.minimax_client import MiniMaxAPIError, chat_completion


SYSTEM_PROMPT = """你是 FinDataPilot 的金融数据助手，性格亲切、表达自然，像一个懂行的同学/学长在帮用户拆解问题。

你的任务：把系统已经调用 QUERY2DATA 拿到的结构化结果，翻译成"人话"——既要答得准，也要读起来舒服。用户看到的不是冷冰冰的取数报告，而是有人情味的分析。

# 写作风格（这是核心）

1. **开篇直接给结论**：第一句就把用户最关心的具体数值/票名/日期/百分比写出来，加粗。
   - 格式：`**结论：……**`
   - 末尾可自然点缀一个 emoji（📌 最常见，🙂、🤔 也可），每段最多 1 个。
   - 没有数据时写 `**结论：未返回符合条件的数据。**`

2. **像人说话，不要堆列表**：结论之后用 1-3 段自然语言解释"我为什么这么判断 / 数据来自哪 / 这意味着什么"。避免把所有内容都拆成 1. 2. 3. 的编号列表，段落里该用逗号、句号就用。

3. **只在用户问"怎么筛/怎么算"时才用小标题**：如果用户的问句涉及多条件筛选、排序、计算题，可以加 `---` 分隔，然后用 `## 筛选口径` / `## 计算步骤` / `## 数据明细` 简短说明，每节 1-3 句即可，不要写成长篇大论。
   - 计算题可用 LaTeX 公式 `\[ ... \]`。
   - 表格用 Markdown `| col | col |`，行数 ≤ 8 行（更多交给前端可视化）。
   - 补充说明用 `>` 引用块，1-2 句解释口径/单位/可能偏差。

4. **结尾必须带"追问建议"**：以 `想不想我……？` / `如果你愿意，我可以……` / `要不要我再……` 收尾，主动抛 1 个（最多 2 个）用户可能感兴趣的延伸方向，**以问号结束**。
   - 简单问句也要带这一句。
   - 延伸方向要具体、可执行：换时间窗、加指标、按行业分组、对比 Top N、拆出"主连 vs 全部"、换排序方式等。

5. **标点和量词**：`+0.03%`、`约 49.96%`、`15 只`、`1,643 家`、`约 7.0018 亿份`——符合中文金融写作习惯。

6. **不要**：JSON 块、`<apply>` 标签、代码块（除非内嵌 reference_v2 数据引用）、投资建议（"建议买入/卖出"）、编造 preview 中不存在的数字、修改日期字段的年份。

# 风格参考（学习这个语气，不要照抄内容）

**A. 简单取数**
> **结论：上银转债（113042.SH）在 2025-12-19 的涨跌幅为：+0.03%**（精确值约 +0.029116%）。这只可转债当天的波动非常小，几乎和前一天持平，市场对它的关注度也不高。
>
> 想不想我顺便把近 20 个交易日的涨跌幅序列也拉出来，帮你看看它那段时间是偏强还是偏弱？

**B. 多条件筛选**
> **结论：满足你给的条件（2025-04-01 当日：MA5>MA10>MA20>MA30>MA60，且 MACD/RSI/KDJ 同时金叉）的 A 股一共 15 只。**📌 这 15 只都属于"趋势刚转强 + 三指标同时确认"的形态，短线资金关注度通常比较高。
>
> 筛选逻辑上，我严格按你给的 7 个条件交叉：A 股全市场、日期锁 2025-04-01、均线严格多头排列、MACD/RSI/KDJ 三金叉同时成立。
>
> 如果你更想看的是"主升浪初期"那种更窄的形态，我可以再叠加"当日涨幅 > 0%"或"近 5 日资金净流入为正"做二次过滤，要不要试试？

**C. 计算型**
> **结论：2024 年前三季度，深圳市进出口贸易总额占广东省的比例约为 49.96%，差不多是"半壁江山"。**
>
> 算法很简单：深圳前三季度进出口 33720.85 亿元 ÷ 广东全省 67500 亿元 ≈ 49.96%。这两个数都是从问财 query2data 取的官方口径，单位是亿元人民币。
>
> 想不想我顺手把"深圳出口/进口分别占广东的比例"一起算出来，方便你做进出口结构的对比？

# 其它约束

- 默认中文。用户用英文就回英文，其它语言同理。
- 不确定日期含义时保留原始字段名（如 `20260521` 不要改成"2025 年"）。
- 你不能"调代码"或"装库"，所有数据都来自 `table.preview / source / plan / warnings`。
- 如果 `table.rows == 0`，禁止编造结果，结论直接写"未返回符合条件的数据"，追问建议改为"想不想换个更宽松的口径再试一次？"。
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
            timeout=30,
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
    if normalized["need_clarification"] and looks_actionable_financial_query(user_query):
        normalized["task_type"] = fallback["task_type"]
        normalized["need_clarification"] = False
        normalized["clarification"] = ""
        normalized["query"] = str(normalized.get("query") or user_query).strip() or user_query
    if not isinstance(normalized.get("clarification"), str):
        normalized["clarification"] = ""
    return normalized


def looks_actionable_financial_query(query: str) -> bool:
    normalized = query.strip().lower()
    if not normalized:
        return False
    object_keywords = (
        "自选股", "持仓", "股票", "基金", "指数", "etf", "a股", "港股", "美股",
        "板块", "行业", "概念", "市场",
    )
    metric_keywords = (
        "涨跌幅", "涨幅", "跌幅", "行情", "收盘价", "最新价", "成交量", "成交额",
        "市值", "pe", "净利润", "roe", "表现", "情况", "排名", "走势",
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
                        "请按 SYSTEM_PROMPT 的人情味风格生成最终回答：\n"
                        "1. 第一行必须是 `**结论：……**`，把用户最关心的具体数值/票名/日期写出来；"
                        "table.rows 为 0 时直接写 `**结论：未返回符合条件的数据。**`。\n"
                        "2. 紧跟 1-3 段自然语言解释，**避免把所有内容都写成 1./2./3. 编号列表**——该用段落就用段落。\n"
                        "3. 仅在用户问题涉及多条件筛选/排序/TopN/计算时，才用 `---` 分隔并加 `## 筛选口径` / `## 计算步骤` / `## 数据明细` 小节，"
                        "每节 1-3 句即可。补充说明用 `>` 引用块。\n"
                        "4. **必须**以一句「想不想我……？」或「要不要我再……」风格的追问建议结尾，问号结束。\n"
                        "5. 不输出代码块、JSON、<apply>、投资建议；不编造 preview 中不存在的数值；不修改日期字段的年份。\n"
                        "6. 默认中文；emoji 自然点缀（每节最多 1 个）。\n"
                        + json.dumps(compact_payload, ensure_ascii=False)
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=1600,
            timeout=30,
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
            "headline": "一句话加粗结论，必须包含具体数值/票名/日期",
            "stats": [{"label": "具体字段", "value": "具体值", "hint": "可选说明"}],
            "insights": ["2-5条基于结果的洞察"],
            "result_columns": ["用于可视化表格的列名，最多8列"],
            "result_rows": [{"列名": "值"}],
            "method": ["取数和处理步骤"],
            "warnings": ["注意事项"],
            "criteria": ["筛选/排序/TopN/阈值等口径条件，每条一句，编号风格"],
            "steps": ["计算步骤/取数步骤的子步骤，每条一句，可包含公式描述"],
            "notes": ["补充说明：单位、口径、时间含义、可能偏差，每条一句，用 > 引用块渲染"],
            "followups": ["追问建议，1-2 句『想不想我……？』风格"],
            "chart": "可选图表对象。**只有当可视化确实能帮助用户理解结果时才填**，否则严格填 null。",
            "chart_type": "bar | line | pie | null。bar 用于对比多只股票某数值；line 用于同一标的随时间变化；pie 用于行业/板块/概念分类占比。",
            "chart_reason": "一句话解释『为什么这张图对当前结果有用』；不画图时填 null。",
            "chart_x": "X 轴列名（分类或时间），不画时填 null。",
            "chart_y": "Y 轴列名（数值），不画时填 null。",
            "chart_group": "分类列名（仅 pie 用，bar/line 填 null），不画时填 null。",
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
                        "3. headline 必须是一句话加粗结论，**直接给出具体数值/票名/日期**，与系统提示词中 `**结论：……**` 风格一致；"
                        "4. stats 必须展示结构化结果里的具体数据值，例如首条记录的股票简称、涨跌幅、收盘价、日期等；"
                        "不要把总行数、字段数、表头名当作主要 stats；"
                        "5. insights 用业务语言解释结果，适合放入“结果要点”，但不能给投资建议；"
                        "6. method 写清取数、筛选、排序、二次处理和校验口径；"
                        "7. warnings 写真实限制，没有则为“暂无额外告警”；"
                        "8. criteria 写筛选/排序/TopN/阈值等口径条件（编号风格），若无筛选则为空数组；"
                        "9. steps 写计算步骤或取数步骤的子步骤（如果用户问题没有计算则留空数组）；"
                        "10. notes 写补充说明：单位、口径、时间含义、可能偏差；"
                        "11. followups 写 1-2 句「想不想我……？」风格的追问建议；"
                        "12. 如果 table.rows 为 0，不得构造 result_rows，必须在 headline/warnings 说明无非空数据；"
                        "13. **chart 决策（重点）**：按以下规则二选一，宁缺毋滥："
                        "    - **不画**（chart=null, chart_reason=null）：单值取数、1 条结果、纯文本/单行元信息、用户明确只问『是什么/多少』；"
                        "    - **画 bar**：≥8 条结果 + 含可对比的数值列（涨跌幅/最新价/最新涨跌幅/成交额/市值/换手率等）→ 必须填 bar；chart_x 用股票简称/股票代码/名称/日期这类分类列，chart_y 用那个数值列，reason 写一句『横向对比 N 条结果的 Y 指标』；"
                        "    - **画 line**：结果含日期列 + 同一指标 ≥3 个时间点 → 填 line；chart_x=日期，chart_y=数值；"
                        "    - **画 pie**：含可分组列（行业/板块/概念/分组），分组数 ≥3 → 填 pie；chart_group=分组列名，chart_x 留空，chart_y 留空；"
                        "    - 多个候选时只画一种最有信息量的；选 bar 时 bar 是默认兜底（用户最常看的就是『哪些股票排前面』）。\n"
                        + json.dumps(compact_payload, ensure_ascii=False)
                    ),
                },
            ],
            temperature=0.1,
            max_tokens=1400,
            timeout=60,
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
    public_warnings = [w for w in (source.get("warnings") or []) if not _is_internal_warning(w)]
    row_count = table.get("rows") or 0
    if not row_count:
        return "**结论：未返回符合条件的数据。**\n\n要不要我换个更宽松的筛选口径再试一次？"

    first_row = (table.get("preview") or [{}])[0]
    columns = table.get("columns") or []
    headline_value = _pick_first_value(first_row, columns, user_query)
    lead = _build_lead(user_query=_safe_query(user_query), table=table, headline_value=headline_value)

    data_query = source.get("data_query") or user_query
    time_range = (source.get("llm_plan") or {}).get("time_range") or "最新可得"
    criteria = _build_criteria_from_plan(source)
    is_screening = _looks_like_screening(user_query, row_count)

    # 主体段落：把"为什么这么判断 / 数据来自哪"用自然语言说清楚
    if is_screening:
        body = (
            f"我按你给的问句去问财 query2data 跑了一遍（实际取数问句：`{data_query}`），"
            f"时间口径是 **{time_range}**，命中条件如上述结论，共 {row_count} 条结果。"
        )
    else:
        body = (
            f"这个数是从问财 query2data 取的（取数问句：`{data_query}`，时间口径：**{time_range}**），"
            f"数据接口返回了 {row_count} 条结构化记录。"
        )

    parts: list[str] = [lead, body]

    if is_screening and criteria:
        parts.append("---")
        parts.append("## 筛选口径（我按这个逻辑跑的）")
        parts.extend(f"{idx}. {item}" for idx, item in enumerate(criteria, 1))

    columns_hint = _compact_columns(table)
    if columns_hint:
        parts.append("---")
        parts.append("## 数据明细")
        parts.append(columns_hint)

    note_lines = ["字段单位以列名为准，前端只展示了前 50 行预览。"]
    if public_warnings:
        note_lines.append("；".join(public_warnings))
    parts.append("---")
    parts.append("## 补充说明")
    parts.append("> " + " ".join(note_lines))

    parts.append(_default_followup(user_query))
    return "\n\n".join(parts)


def _build_lead(*, user_query: str, table: dict[str, Any], headline_value: str) -> str:
    row_count = table.get("rows") or 0
    if not headline_value:
        return f"**结论：问题「{user_query}」已返回 {row_count} 行结构化数据。**"
    field, value = headline_value.split("=", 1) if "=" in headline_value else ("", headline_value)
    field_lower = field.lower()
    subject_match = _extract_subject(user_query)
    is_screening = _looks_like_screening(user_query, row_count)
    # For multi-condition screening queries, lead with hit count.
    if is_screening:
        emoji = "📌" if row_count > 0 else ""
        return f"**结论：满足筛选条件的标的共有 {row_count} 只。**{(' ' + emoji) if emoji else ''}"

    if field in ("董事长", "总经理", "CEO", "ceo", "基金经理", "现任基金经理", "管理人") and subject_match:
        return f"**结论：{subject_match}的{field}是：{value}。**"
    if any(k in field for k in ("董事长", "总经理", "CEO", "ceo", "基金经理", "管理人")) and subject_match:
        return f"**结论：{subject_match}的{field}是：{value}。**"
    if any(k in field_lower for k in ("涨跌幅", "涨幅", "跌幅")) and subject_match and len(subject_match) <= 12:
        return f"**结论：{subject_match}的{field}为 {value}。**"
    if any(k in field_lower for k in ("最新价", "收盘价", "现价", "价格", "净值", "份额")) and subject_match and len(subject_match) <= 12:
        return f"**结论：{subject_match}的{field}为 {value}。**"
    if any(k in field_lower for k in ("销售净利率", "净利率", "市净率", "市盈率", "股息率", "roe", "pb", "pe")) and subject_match and len(subject_match) <= 12:
        return f"**结论：{subject_match}的{field}为 {value}。**"
    if any(k in field for k in ("股票简称", "证券简称", "简称", "名称")):
        return f"**结论：问题「{user_query}」已返回 {row_count} 行结构化数据，命中标的为 {value}。**"
    return f"**结论：问题「{user_query}」已返回 {row_count} 行结构化数据，首条关键字段 {field}={value}。**"


def _looks_like_screening(user_query: str, row_count: int) -> bool:
    """Heuristic: a screening query has multiple conditions or uses ranking words."""
    if row_count <= 0:
        return False
    screening_markers = (
        "大于", "小于", "超过", "高于", "低于", "以内", "排名", "前", "金叉", "死叉",
        "多头", "空头", "均线", "换手率", "振幅", "涨幅大于", "跌幅大于", "筛选", "选出",
    )
    count = sum(1 for marker in screening_markers if marker in user_query)
    return count >= 2


def _extract_subject(user_query: str) -> str:
    """Best-effort extract the subject (a stock/fund/etf/index/company name) from a Chinese query."""
    cleaned = user_query.strip()
    for sep in ("的", "是", "在", "于", "为", "，", ",", "。", "？", "?", " "):
        if sep in cleaned:
            cleaned = cleaned.split(sep, 1)[0]
            break
    cleaned = cleaned.strip()
    if not cleaned:
        return ""
    return cleaned


def _safe_query(q: str) -> str:
    """Truncate very long query strings so headlines stay readable."""
    return q if len(q) <= 40 else q[:40] + "…"


def _is_internal_warning(warning: str) -> bool:
    """Filter out internal/diagnostic warnings that shouldn't be shown to end users."""
    if not warning:
        return True
    text = warning.lower()
    internal_markers = (
        "minimax", "anthropic", "openai", "http 401", "http 403", "http 429",
        "http 5", "api key", "apikey", "summary failed",
    )
    return any(marker in text for marker in internal_markers)


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

    criteria = _build_criteria_from_plan(source)
    notes = []
    if source.get("data_query"):
        notes.append(f"实际取数问句：{source['data_query']}")
    if source.get("status_code") is not None:
        notes.append(f"接口返回 status_code = {source.get('status_code')}")
    notes.append("字段单位以列名为准，前端仅展示部分预览。")

    public_warnings = [w for w in warnings if not _is_internal_warning(w)]

    # Local fallback chart decision: conservative. Only emit a bar chart when
    # the data clearly supports comparison (≥5 ranked rows + numeric col).
    chart_obj = _local_chart_decision(query_type, rows, selected_columns)

    return {
        "title": _visual_title(query_type),
        "query_type": query_type,
        "headline": _compact_intro(user_query, table, source),
        "stats": stats[:6],
        "insights": insights[:5],
        "result_columns": selected_columns,
        "result_rows": visual_rows,
        "method": [str(item) for item in (plan.get("steps") or [])[:5]],
        "criteria": criteria,
        "steps": [str(item) for item in (plan.get("post_process") or [])[:5]],
        "notes": notes,
        "followups": [_default_followup_question(user_query)],
        "warnings": public_warnings or ["暂无额外告警。"],
        "chart": chart_obj,
    }


def _local_chart_decision(query_type: str, rows: list[dict[str, Any]], columns: list[str]) -> dict[str, Any] | None:
    """Conservative default. Returns None unless a chart is clearly useful."""
    if len(rows) < 5 or not columns:
        return None
    # Pick a numeric y column from common candidates.
    y_candidates = (
        "涨跌幅", "最新涨跌幅", "涨幅", "收益率",
        "最新价", "收盘价", "现价", "价格",
        "成交额", "市值", "总市值", "流通市值",
        "市盈率", "PE", "换手率",
    )
    y_col = next(
        (c for c in columns if any(k == c or k in c for k in y_candidates) and any(_is_numberish(row.get(c)) for row in rows)),
        "",
    )
    if not y_col:
        return None
    x_candidates = ("股票简称", "证券简称", "名称", "股票代码", "证券代码", "代码", "日期", "时间")
    x_col = next((c for c in columns if any(k == c or k in c for k in x_candidates)), "")
    if not x_col:
        return None
    if query_type not in ("stock_selection", "ranking", "data_query", "analysis"):
        return None
    return {
        "type": "bar",
        "x": x_col,
        "y": y_col,
        "group": "",
        "reason": f"本地兜底：{len(rows)} 条结果含可比数值列『{y_col}』，默认给一张柱状对比图。",
    }


def _is_numberish(value: Any) -> bool:
    if isinstance(value, (int, float)):
        return not isinstance(value, bool)
    if not isinstance(value, str):
        return False
    cleaned = value.replace("%", "").replace(",", "").replace("万", "").replace("亿", "").strip()
    if not cleaned:
        return False
    try:
        float(cleaned)
        return True
    except ValueError:
        return False


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
    for key in ("stats", "insights", "result_columns", "result_rows", "method", "warnings", "criteria", "steps", "notes", "followups"):
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
    visual["criteria"] = [str(item) for item in visual["criteria"] if str(item).strip()][:8]
    visual["steps"] = [str(item) for item in visual["steps"] if str(item).strip()][:8]
    visual["notes"] = [str(item) for item in visual["notes"] if str(item).strip()][:6]
    visual["followups"] = [str(item) for item in visual["followups"] if str(item).strip()][:4]
    visual["warnings"] = [str(item) for item in visual["warnings"] if str(item).strip()] or ["暂无额外告警。"]
    # Chart decision: LLM may return null to suppress charts entirely.
    chart_type = str(visual.get("chart_type") or "").strip().lower()
    valid_types = ("bar", "line", "pie")
    if chart_type not in valid_types:
        chart_type = ""
    chart_x = str(visual.get("chart_x") or "").strip() if chart_type in ("bar", "line", "pie") else ""
    chart_y = str(visual.get("chart_y") or "").strip() if chart_type in ("bar", "line") else ""
    chart_group = str(visual.get("chart_group") or "").strip() if chart_type == "pie" else ""
    chart_reason = str(visual.get("chart_reason") or "").strip() if chart_type else ""
    # Drop the chart entirely if required fields are missing.
    if chart_type and not chart_x and chart_type != "pie":
        chart_type = ""
    if chart_type and chart_type != "pie" and not chart_y:
        chart_type = ""
    if chart_type == "pie" and not (chart_x or chart_group):
        chart_type = ""
    if chart_type:
        visual["chart"] = {
            "type": chart_type,
            "x": chart_x,
            "y": chart_y,
            "group": chart_group,
            "reason": chart_reason,
        }
    else:
        visual["chart"] = None
    # Strip the auxiliary chart fields so the JSON stays compact.
    for key in ("chart_type", "chart_x", "chart_y", "chart_group", "chart_reason"):
        visual.pop(key, None)
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
        first_row = (table.get("preview") or [{}])[0]
        columns = table.get("columns") or []
        lead_value = _pick_first_value(first_row, columns, user_query)
        if lead_value:
            return _build_lead(user_query=_safe_query(user_query), table=table, headline_value=lead_value)
        return f"**结论：问题「{user_query}」已返回 {rows} 行结构化数据。**"
    return "**结论：未返回符合条件的数据。**"


def _pick_first_value(first_row: dict[str, Any], columns: list[str], user_query: str = "") -> str:
    # When the user asks "X 的董事长/总经理/基金经理是谁", prefer the 姓名 + 职务 pair.
    query_lower = (user_query or "").lower()
    if any(k in user_query for k in ("是谁", "是谁？", "是谁?")) and any(role in user_query for role in ("董事长", "总经理", "ceo", "CEO", "基金经理", "管理人", "法定代表人")):
        name_value = None
        title_value = None
        for column in columns:
            if "姓名" in column and first_row.get(column) not in (None, ""):
                name_value = first_row[column]
            if "职务" in column and first_row.get(column) not in (None, ""):
                title_value = first_row[column]
        if name_value and title_value:
            return f"{title_value}={name_value}"

    priority = (
        "最新涨跌幅", "涨跌幅", "涨幅", "跌幅",
        "最新价", "收盘价", "现价", "价格",
        "单位净值", "累计净值", "净值",
        "基金份额", "份额",
        "销售净利率", "净利率", "市净率", "PB", "PE", "市盈率", "股息率", "ROE",
        "股票简称", "证券简称", "简称", "名称",
        "股票代码", "证券代码", "代码",
    )
    lowered_columns = [(c, c.lower()) for c in columns]
    for key in priority:
        key_lower = key.lower()
        for column, column_lower in lowered_columns:
            if key_lower in column_lower and column in first_row:
                value = first_row[column]
                if value not in (None, ""):
                    return f"{column}={value}"
    for column in columns[:4]:
        value = first_row.get(column)
        if value not in (None, ""):
            return f"{column}={value}"
    return ""


def _build_criteria_from_plan(source: dict[str, Any]) -> list[str]:
    plan = source.get("llm_plan") or {}
    items: list[str] = []
    data_query = source.get("data_query") or plan.get("query")
    if data_query:
        items.append(f"实际取数问句：{data_query}")
    time_range = plan.get("time_range")
    if time_range:
        items.append(f"时间范围：{time_range}")
    for metric in (plan.get("metrics") or [])[:3]:
        items.append(f"核心指标：{metric}")
    filters = plan.get("filters") or []
    for f in filters[:3]:
        items.append(f"筛选条件：{f}")
    if plan.get("analysis"):
        items.append(f"二次加工：本地执行 {plan['analysis']} 计算")
    return items


def _default_followup(user_query: str) -> str:
    return f"要不要我顺着「{user_query}」再细化一下口径？比如换个时间窗、加个指标，或者换一种排序方式试试？"


def _default_followup_question(user_query: str) -> str:
    return f"要不要我顺着「{user_query}」再细化一下口径？比如换个时间窗、加个指标，或者换一种排序方式试试？"


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
