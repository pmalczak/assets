# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date

import pandas as pd


def filter_on_or_before(df: pd.DataFrame, date_column: str, valuation_date: date) -> pd.DataFrame:
    if df.empty or date_column not in df.columns:
        return df.copy()

    parsed = pd.to_datetime(df[date_column], errors="coerce").dt.normalize()
    cutoff = pd.Timestamp(valuation_date).normalize()
    return df.loc[parsed <= cutoff].copy()


def filter_excel_rows_on_or_before(df: pd.DataFrame, date_column: str, valuation_date: date) -> pd.DataFrame:
    if df.empty or date_column not in df.columns:
        return df.copy()

    work = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(work[date_column]):
        work[date_column] = pd.to_datetime(work[date_column], errors="coerce")
    cutoff = pd.Timestamp(valuation_date).normalize()
    return work.loc[work[date_column].dt.normalize() <= cutoff].copy()


def format_date_columns(df: pd.DataFrame, *columns: str) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    result = df.copy()
    for column in columns:
        if column not in result.columns:
            continue
        result[column] = pd.to_datetime(result[column], errors="coerce").dt.strftime("%Y-%m-%d")
    return result
