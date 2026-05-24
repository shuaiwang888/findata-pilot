from __future__ import annotations

from dataclasses import dataclass


@dataclass
class QueryPlan:
    task_type: str
    query: str
    analysis: str | None = None
    need_clarification: bool = False
    clarification: str | None = None


ANALYSIS_KEYWORDS = {
    "moving_average": ("均线", "移动平均", "ma"),
    "return": ("收益率", "涨跌幅", "涨幅", "跌幅"),
    "volatility": ("波动率", "标准差"),
    "max_drawdown": ("最大回撤", "回撤"),
}


def plan_query(query: str) -> QueryPlan:
    normalized = query.strip().lower()
    if not normalized:
        return QueryPlan(
            task_type="need_clarification",
            query=query,
            need_clarification=True,
            clarification="请输入需要查询的金融取数问题。",
        )

    for analysis, keywords in ANALYSIS_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            return QueryPlan(task_type="query_then_analyze", query=query, analysis=analysis)

    return QueryPlan(task_type="direct_query", query=query)

