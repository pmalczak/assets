# -*- coding: utf-8 -*-
"""Parquet I/O bez wątków pyarrow — omija segfault convert_column (pandas 3 str).

Daty domenowe: przy zapisie/odczycie kolumny ``datetime64`` (i znane nazwy) → ISO ``YYYY-MM-DD``.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from evaluators.valuation_date import to_iso_date_series

# Kolumny często trzymane jako object/string, ale mogą wrócić z Excela/parquet jako datetime.
_KNOWN_DATE_COLUMNS = frozenset(
    {
        "data wyceny",
        "data-waluty",
        "data-wyciągu",
        "data-ostatniej-transakcji",
        "Data",
        "DATE",
        "date",
        "VALUE_DATE",
        "FILE_DATE",
        "PERIOD_START",
        "PERIOD_END",
        "evaluation_date",
        "STATEMENT_DATE",
    }
)


def dataframe_for_parquet(df: pd.DataFrame) -> pd.DataFrame:
    """Ramka z kolumnami numpy/object — bez StringDtype/ArrowDtype w wątkach pyarrow."""
    out = normalize_date_columns_for_parquet(df)
    for col in out.columns:
        out[col] = _series_for_parquet(out[col])
    return out


def normalize_date_columns_for_parquet(df: pd.DataFrame) -> pd.DataFrame:
    """Force date-like columns to ISO strings for a predictable parquet round-trip."""
    if df.empty:
        return df.copy()
    out = df.copy()
    for col in out.columns:
        if _should_normalize_date_column(out[col], str(col)):
            out[col] = to_iso_date_series(out[col])
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


def read_dataframe_parquet(
    path: Path | str,
    *,
    columns: list[str] | None = None,
) -> pd.DataFrame:
    """Read parquet and normalize date-like columns to ISO strings."""
    kwargs: dict = {}
    if columns is not None:
        kwargs["columns"] = columns
    loaded = pd.read_parquet(path, **kwargs)
    return normalize_date_columns_for_parquet(loaded)


def _should_normalize_date_column(series: pd.Series, name: str) -> bool:
    if pd.api.types.is_datetime64_any_dtype(series.dtype):
        return True
    return name in _KNOWN_DATE_COLUMNS


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
    # Datetime already converted to ISO in normalize_date_columns_for_parquet.
    return pd.api.types.is_numeric_dtype(dtype)


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
