# -*- coding: utf-8 -*-
"""Zapis parquet bez wątków pyarrow — omija segfault convert_column (pandas 3 str)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


def dataframe_for_parquet(df: pd.DataFrame) -> pd.DataFrame:
    """Ramka z kolumnami numpy/object — bez StringDtype/ArrowDtype w wątkach pyarrow."""
    out = df.copy()
    for col in out.columns:
        out[col] = _series_for_parquet(out[col])
    return out


def write_dataframe_parquet(
    df: pd.DataFrame,
    path: Path | str,
    *,
    compression: str | None = None,
) -> None:
    safe = dataframe_for_parquet(df)
    table = pa.Table.from_pandas(safe, nthreads=1)
    pq.write_table(table, path, compression=compression)


def _series_for_parquet(series: pd.Series) -> pd.Series:
    if _keep_numeric_or_datetime(series.dtype):
        return series
    values = [_pythonize(v) for v in series.tolist()]
    if _mixed_scalar_types(values):
        values = [None if v is None else str(v) for v in values]
    return pd.Series(values, index=series.index, dtype=object)


def _keep_numeric_or_datetime(dtype) -> bool:
    if pd.api.types.is_bool_dtype(dtype):
        return False
    return pd.api.types.is_numeric_dtype(dtype) or pd.api.types.is_datetime64_any_dtype(dtype)


def _pythonize(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (ValueError, TypeError):
        pass
    if hasattr(value, "item") and not isinstance(value, (bytes, bytearray, str)):
        try:
            return value.item()
        except (ValueError, AttributeError):
            pass
    return value


def _mixed_scalar_types(values: list) -> bool:
    types = {type(v) for v in values if v is not None}
    return len(types) > 1 and not types <= {str, bytes, bytearray}
