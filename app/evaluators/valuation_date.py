# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd


def to_iso_date(value: Any) -> str | None:
    """Normalize a scalar to calendar ``YYYY-MM-DD``, or ``None`` if unusable.

    Timezone-aware values use the UTC calendar day (no local shift for cutoff).
    """
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (ValueError, TypeError):
        pass

    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if len(text) >= 10 and text[4] == "-" and text[7] == "-":
            try:
                return date.fromisoformat(text[:10]).isoformat()
            except ValueError:
                pass

    ts = pd.Timestamp(value) if isinstance(value, datetime) else pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return None
    if getattr(ts, "tz", None) is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts.date().isoformat()

def as_iso_date(valuation_date: date | datetime | str | pd.Timestamp) -> str:
    """Cutoff helper: always a concrete ``YYYY-MM-DD`` string."""
    iso = to_iso_date(valuation_date)
    if iso is None:
        raise ValueError(f"Niepoprawna data wyceny: {valuation_date!r}")
    return iso


def to_iso_date_series(series: pd.Series) -> pd.Series:
    """Vectorized ``to_iso_date``; invalid → ``<NA>`` (pandas StringDtype / object NA)."""
    if series.empty:
        return pd.Series(dtype=object)
    values = [to_iso_date(v) for v in series.tolist()]
    return pd.Series(values, index=series.index, dtype=object)


def normalize_iso_date_columns(df: pd.DataFrame, *columns: str) -> pd.DataFrame:
    """Return a copy with named columns coerced to ISO date strings (invalid → ``None``)."""
    if df.empty:
        return df.copy()
    result = df.copy()
    for column in columns:
        if column not in result.columns:
            continue
        result[column] = to_iso_date_series(result[column])
    return result


def filter_on_or_before(
    df: pd.DataFrame,
    date_column: str,
    valuation_date: date | datetime | str | pd.Timestamp,
) -> pd.DataFrame:
    """Keep rows whose date column (any common type) is ``<=`` valuation calendar day."""
    if df.empty or date_column not in df.columns:
        return df.copy()

    cutoff = as_iso_date(valuation_date)
    iso = to_iso_date_series(df[date_column])
    mask = iso.notna() & (iso <= cutoff)
    return df.loc[mask].copy()


def filter_excel_rows_on_or_before(
    df: pd.DataFrame,
    date_column: str,
    valuation_date: date | datetime | str | pd.Timestamp,
) -> pd.DataFrame:
    """Alias of ``filter_on_or_before`` (single ISO-string comparison path)."""
    return filter_on_or_before(df, date_column, valuation_date)


def format_date_columns(df: pd.DataFrame, *columns: str) -> pd.DataFrame:
    """Normalize date columns to ISO strings for parquet / UI (invalid → ``None``)."""
    return normalize_iso_date_columns(df, *columns)
