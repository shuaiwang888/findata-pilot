from __future__ import annotations

import re
from typing import Any

import pandas as pd


def _numeric_series(df: pd.DataFrame, preferred_patterns: tuple[str, ...]) -> tuple[str | None, pd.Series | None]:
    for pattern in preferred_patterns:
        for column in df.columns:
            if pattern in str(column):
                series = pd.to_numeric(df[column], errors="coerce")
                if series.notna().sum() > 0:
                    return str(column), series

    for column in df.columns:
        series = pd.to_numeric(df[column], errors="coerce")
        if series.notna().sum() > 1:
            return str(column), series
    return None, None


def _window_from_query(query: str, default: int = 20) -> int:
    match = re.search(r"(\d+)\s*(?:日|天|个交易日)?\s*(?:均线|移动平均|ma)", query, re.I)
    if match:
        return max(1, int(match.group(1)))
    return default


def analyze_dataframe(df: pd.DataFrame, query: str, analysis: str | None) -> tuple[pd.DataFrame, list[str], dict[str, Any]]:
    if analysis is None:
        return df, [], {}

    result = df.copy().reset_index(drop=True)
    warnings: list[str] = []
    info: dict[str, Any] = {"analysis": analysis}

    column_name, series = _numeric_series(result, ("收盘价", "最新价", "涨跌幅"))
    if series is None or column_name is None:
        return result, [f"未找到可用于 {analysis} 的数值列，已返回原始数据。"], info

    info["source_column"] = column_name

    if analysis == "moving_average":
        window = _window_from_query(query)
        result[f"{column_name}_{window}日均线"] = series.rolling(window=window, min_periods=1).mean()
        info["window"] = window
    elif analysis == "return":
        result[f"{column_name}_环比收益率"] = series.pct_change()
    elif analysis == "volatility":
        result[f"{column_name}_波动率"] = series.pct_change().rolling(window=min(20, len(result)), min_periods=2).std()
    elif analysis == "max_drawdown":
        running_max = series.cummax()
        drawdown = series / running_max - 1
        result[f"{column_name}_回撤"] = drawdown
        info["max_drawdown"] = None if drawdown.dropna().empty else float(drawdown.min())
    else:
        warnings.append(f"暂不支持分析类型 {analysis}，已返回原始数据。")

    return result.reset_index(drop=True), warnings, info

