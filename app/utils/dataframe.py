from __future__ import annotations

from pathlib import Path
from typing import Any
import math

import pandas as pd


def clean_json_value(value: Any) -> Any:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, dict):
        return {key: clean_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clean_json_value(item) for item in value]
    return value


def dataframe_preview(df: pd.DataFrame, limit: int = 10) -> list[dict[str, Any]]:
    preview = df.head(limit).replace({pd.NA: None}).to_dict(orient="records")
    return clean_json_value(preview)


def save_dataframe(
    df: pd.DataFrame,
    trace_id: str,
    output_dir: str,
) -> tuple[str | None, str | None, list[str]]:
    warnings: list[str] = []
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    csv_path = output_path / f"{trace_id}.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    parquet_path = output_path / f"{trace_id}.parquet"
    try:
        df.to_parquet(parquet_path, index=False)
        parquet_value: str | None = str(parquet_path)
    except Exception as exc:
        parquet_value = None
        warnings.append(f"Parquet save skipped: {exc}")

    return str(csv_path), parquet_value, warnings
