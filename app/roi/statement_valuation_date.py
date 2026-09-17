# -*- coding: utf-8 -*-
"""Data wyceny ROI = data pobrania użytego pliku, ograniczona datą obliczenia."""
from __future__ import annotations

from datetime import date

import pandas as pd

from importers.assets.data_model import AssetsDef


def evaluation_date_from_file_dates(file_dates, calculation_date: date) -> str | None:
    """`min(data obliczenia ROI, max(FILE_DATE))`; None gdy brak poprawnej daty źródła."""
    if file_dates is None:
        return None
    series = file_dates if isinstance(file_dates, pd.Series) else pd.Series(file_dates)
    parsed = pd.to_datetime(series, errors="coerce")
    last = parsed.max()
    if pd.isna(last):
        return None
    return min(calculation_date, last.date()).isoformat()


def evaluation_date_from_frame(
    df: pd.DataFrame | None,
    column: str,
    calculation_date: date,
) -> str | None:
    if df is None or df.empty or column not in df.columns:
        return None
    return evaluation_date_from_file_dates(df[column], calculation_date)


def attach_evaluation_date(row: dict, evaluation_date: str | None) -> dict:
    row[AssetsDef.EVALUATION_DATE] = evaluation_date or ""
    return row
