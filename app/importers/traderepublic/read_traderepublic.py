# -*- coding: utf-8 -*-
from __future__ import annotations

__author__ = "pmalczak@gmail.com"

import re
from datetime import date
from pathlib import Path

import pandas as pd

from data_step.data_step import DATA_STEP
from importers.period_coverage import assert_no_coverage_gaps
from importers.traderepublic.data_model import (
    FILE_PREFIX,
    REQUIRED_SOURCE_COLUMNS,
    TradeRepublicFile,
)

_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_FILENAME_RE = re.compile(
    rf"^{re.escape(FILE_PREFIX)}_(\d{{4}}-\d{{2}}-\d{{2}})_(\d{{4}}-\d{{2}}-\d{{2}})$"
)


def is_traderepublic_export_header(columns: list[str] | pd.Index) -> bool:
    cols = {str(c).strip() for c in columns}
    return set(REQUIRED_SOURCE_COLUMNS).issubset(cols)


def period_from_dataframe(df: pd.DataFrame) -> tuple[date, date]:
    if df is None or df.empty or TradeRepublicFile.DATE not in df.columns:
        raise ValueError("Brak kolumny date lub pusty eksport Trade Republic")
    parsed = pd.to_datetime(df[TradeRepublicFile.DATE], errors="coerce")
    if parsed.isna().all():
        raise ValueError("Brak poprawnych dat w eksporcie Trade Republic")
    start = parsed.min().date()
    end = parsed.max().date()
    return start, end


def dated_export_filename(period_start: date, period_end: date) -> str:
    return f"{FILE_PREFIX}_{period_start.isoformat()}_{period_end.isoformat()}.csv"


def extract_export_period(path: Path) -> tuple[date, date]:
    match = _FILENAME_RE.fullmatch(path.stem)
    if not match:
        raise ValueError(f"Unexpected Trade Republic export name: {path.name}")
    start_s, end_s = match.group(1), match.group(2)
    if not _DATE_PATTERN.match(start_s) or not _DATE_PATTERN.match(end_s):
        raise ValueError(f"Unexpected dates in {path.name}")
    return date.fromisoformat(start_s), date.fromisoformat(end_s)


def read_traderepublic_transactions(input_path: Path, asset_id: str) -> pd.DataFrame:
    resource = f"01 source/{asset_id}.parquet"
    r = DATA_STEP.obtain_dependent(resource, _read_traderepublic_transactions, input_path)
    return r.data_frame()


def _read_traderepublic_transactions(source_file: Path = None) -> pd.DataFrame:
    input_files = sorted(source_file.rglob(f"{FILE_PREFIX}_*.csv"))
    empty = pd.DataFrame(columns=list(TradeRepublicFile.expected_columns()))
    if not input_files:
        return empty

    periods: list[tuple[date, date]] = []
    records: list[pd.DataFrame] = []
    for input_file in input_files:
        start, end = extract_export_period(input_file)
        periods.append((start, end))
        df = pd.read_csv(input_file)
        if not is_traderepublic_export_header(df.columns):
            raise ValueError(f"Nieoczekiwane kolumny w {input_file.name}")
        df[TradeRepublicFile.PERIOD_START] = start.isoformat()
        df[TradeRepublicFile.PERIOD_END] = end.isoformat()
        df[TradeRepublicFile.FILE_DATE] = end.isoformat()
        print(f"PLIK:{input_file} {len(df):>4} rekord/ów (Trade Republic)")
        records.append(df)

    assert_no_coverage_gaps(periods, asset_id=str(source_file.name), label="eksport-transakcji")

    # Dedupe globalnie po transaction_id (eksporty TR mogą powtarzać ten sam ID
    # poza wąskim oknem overlap dat używanym przez deduplicate_records).
    result = pd.concat(records, ignore_index=True)
    before = len(result)
    result = result.drop_duplicates(subset=TradeRepublicFile.unique_key(), keep="last")
    removed = before - len(result)
    if removed:
        print(f"Trade Republic: usunięto {removed} duplikatów (transaction_id)")

    result["_sort"] = pd.to_datetime(result[TradeRepublicFile.DATE], errors="coerce")
    result = result.sort_values("_sort").drop(columns=["_sort"]).reset_index(drop=True)

    if not result.empty:
        result[TradeRepublicFile.FILE_DATE] = max(p[1] for p in periods).isoformat()

    TradeRepublicFile.check_structure(result)
    return result
