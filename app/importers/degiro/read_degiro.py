# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from data_step.data_step import DATA_STEP
from importers.degiro.data_model import (
    ACCOUNT_PREFIX,
    PORTFOLIO_PREFIX,
    TRANSACTIONS_PREFIX,
    DegiroAccountFile,
    DegiroPortfolioFile,
    DegiroTransactionsFile,
)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATED_RE = re.compile(r"^(?P<prefix>[a-z]+)_(?P<start>\d{4}-\d{2}-\d{2})_(?P<end>\d{4}-\d{2}-\d{2})$")


def parse_degiro_number(value) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return None
    s = s.replace("\xa0", "").replace(" ", "")
    s = s.replace(".", "").replace(",", ".")
    s = re.sub(r"[^\d.\-]", "", s)
    if s in ("", "-", ".", "-."):
        return None
    return float(s)


def parse_degiro_date(value) -> date:
    ts = pd.to_datetime(value, format="%d-%m-%Y", errors="coerce")
    if pd.isna(ts):
        ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        raise ValueError(f"Niepoprawna data DEGIRO: {value!r}")
    return ts.date()


def period_from_account_file(path: Path) -> tuple[date, date]:
    df = read_account_csv(path)
    if df.empty:
        raise ValueError(f"Pusty Account.csv: {path}")
    dates = df[DegiroAccountFile.BOOKING_DATE].map(parse_degiro_date)
    return min(dates), max(dates)


def dated_filename(prefix: str, period_start: date, period_end: date) -> str:
    return f"{prefix}_{period_start.isoformat()}_{period_end.isoformat()}.csv"


def extract_period(path: Path, expected_prefix: str) -> tuple[date, date]:
    match = _DATED_RE.fullmatch(path.stem)
    if not match or match.group("prefix") != expected_prefix:
        raise ValueError(f"Unexpected DEGIRO export name: {path.name}")
    start_s, end_s = match.group("start"), match.group("end")
    if not _DATE_RE.match(start_s) or not _DATE_RE.match(end_s):
        raise ValueError(f"Unexpected DEGIRO dates in {path.name}")
    return date.fromisoformat(start_s), date.fromisoformat(end_s)


def read_portfolio_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    unnamed = [c for c in df.columns if str(c).startswith("Unnamed")]
    if unnamed:
        df = df.rename(
            columns={
                DegiroPortfolioFile.LOCAL_VALUE: DegiroPortfolioFile.LOCAL_CURRENCY,
                unnamed[0]: DegiroPortfolioFile.LOCAL_VALUE,
            }
        )
    else:
        df[DegiroPortfolioFile.LOCAL_CURRENCY] = ""
    return _normalize_portfolio(df)


def read_transactions_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    unnamed = [c for c in df.columns if str(c).startswith("Unnamed")]
    rename = {}
    if len(unnamed) >= 1:
        rename[unnamed[0]] = DegiroTransactionsFile.PRICE_CURRENCY
    if len(unnamed) >= 2:
        rename[unnamed[1]] = DegiroTransactionsFile.LOCAL_VALUE_CURRENCY
    df = df.rename(columns=rename)
    return _normalize_transactions(df)


def read_account_csv(path: Path) -> pd.DataFrame:
    headers = [
        DegiroAccountFile.BOOKING_DATE,
        DegiroAccountFile.TIME,
        DegiroAccountFile.VALUE_DATE,
        DegiroAccountFile.PRODUCT,
        DegiroAccountFile.ISIN,
        DegiroAccountFile.DESCRIPTION,
        DegiroAccountFile.RATE,
        DegiroAccountFile.CHANGE_CURRENCY,
        DegiroAccountFile.CHANGE,
        DegiroAccountFile.BALANCE_CURRENCY,
        DegiroAccountFile.BALANCE,
        DegiroAccountFile.ORDER_ID,
    ]
    df = pd.read_csv(path, skiprows=1, names=headers)
    return _normalize_account(df)


def read_degiro_portfolio(input_path: Path, asset_id: str) -> pd.DataFrame:
    resource = f"01 source/{asset_id}-portfolio.parquet"
    r = DATA_STEP.obtain_dependent(resource, _read_degiro_portfolio, input_path)
    return r.data_frame()


def read_degiro_transactions(input_path: Path, asset_id: str) -> tuple[pd.DataFrame, list[str]]:
    resource = f"01 source/{asset_id}-transactions.parquet"
    r = DATA_STEP.obtain_dependent(resource, _read_degiro_transactions, input_path)
    warnings = period_gap_warnings(_named_periods(input_path, TRANSACTIONS_PREFIX), "transactions")
    return r.data_frame(), warnings


def read_degiro_account(input_path: Path, asset_id: str) -> tuple[pd.DataFrame, list[str]]:
    resource = f"01 source/{asset_id}-account.parquet"
    r = DATA_STEP.obtain_dependent(resource, _read_degiro_account, input_path)
    warnings = period_gap_warnings(_named_periods(input_path, ACCOUNT_PREFIX), "account")
    return r.data_frame(), warnings


def latest_portfolio_as_of(portfolio_df: pd.DataFrame, valuation_date: date) -> pd.DataFrame:
    if portfolio_df.empty:
        return portfolio_df.copy()
    end_dates = pd.to_datetime(portfolio_df[DegiroPortfolioFile.PERIOD_END], errors="coerce").dt.date
    eligible = portfolio_df.loc[end_dates <= valuation_date].copy()
    if eligible.empty:
        return eligible
    latest_end = pd.to_datetime(eligible[DegiroPortfolioFile.PERIOD_END], errors="coerce").max()
    latest = eligible.loc[
        pd.to_datetime(eligible[DegiroPortfolioFile.PERIOD_END], errors="coerce") == latest_end
    ].copy()
    return _one_portfolio_snapshot_per_end(latest)


def _one_portfolio_snapshot_per_end(df: pd.DataFrame) -> pd.DataFrame:
    """Portfolio.csv is a point-in-time snapshot, not a ledger.

    Overlapping exports can share the same PERIOD_END (Account.csv booking window).
    Concatenating them would double MTM. Keep one package per PERIOD_END — the one
    with the latest PERIOD_START — then one row per ISIN (empty ISIN = cash, keyed
    by product).
    """
    if df.empty or DegiroPortfolioFile.PERIOD_END not in df.columns:
        return df
    out = df.copy()
    start = pd.to_datetime(out[DegiroPortfolioFile.PERIOD_START], errors="coerce")
    end = pd.to_datetime(out[DegiroPortfolioFile.PERIOD_END], errors="coerce")
    keep_start = start.groupby(end).transform("max")
    out = out.loc[start.eq(keep_start)].copy()
    isin = out[DegiroPortfolioFile.ISIN].fillna("").astype(str).str.strip()
    product = (
        out[DegiroPortfolioFile.PRODUCT].fillna("").astype(str).str.strip()
        if DegiroPortfolioFile.PRODUCT in out.columns
        else pd.Series("", index=out.index)
    )
    identity = isin.where(isin.ne(""), product)
    row_key = (
        pd.to_datetime(out[DegiroPortfolioFile.PERIOD_END], errors="coerce").astype(str)
        + "|"
        + identity
    )
    return out.loc[~row_key.duplicated(keep="last")].reset_index(drop=True)


def period_gap_warnings(periods: list[tuple[date, date]], label: str) -> list[str]:
    if len(periods) <= 1:
        return []
    ordered = sorted(periods)
    warnings = []
    for prev, nxt in zip(ordered, ordered[1:]):
        gap_start = prev[1] + timedelta(days=1)
        gap_end = nxt[0] - timedelta(days=1)
        if gap_start <= gap_end:
            warnings.append(
                f"Luka w okresach DEGIRO {label}: {gap_start.isoformat()} … {gap_end.isoformat()}"
            )
    return warnings


def _read_degiro_portfolio(source_file: Path = None) -> pd.DataFrame:
    result = _read_many(source_file, PORTFOLIO_PREFIX, read_portfolio_csv, DegiroPortfolioFile)
    return _one_portfolio_snapshot_per_end(result)


def _read_degiro_transactions(source_file: Path = None) -> pd.DataFrame:
    result = _read_many(source_file, TRANSACTIONS_PREFIX, read_transactions_csv, DegiroTransactionsFile)
    if result.empty:
        return result
    result = result.drop_duplicates(subset=DegiroTransactionsFile.unique_key(), keep="last")
    return _sort_by_date(result, DegiroTransactionsFile.DATE)


def _read_degiro_account(source_file: Path = None) -> pd.DataFrame:
    result = _read_many(source_file, ACCOUNT_PREFIX, read_account_csv, DegiroAccountFile)
    if result.empty:
        return result
    result = result.drop_duplicates(subset=DegiroAccountFile.unique_key(), keep="last")
    return _sort_by_date(result, DegiroAccountFile.BOOKING_DATE)


def _read_many(source_file: Path, prefix: str, reader, model) -> pd.DataFrame:
    input_files = sorted(source_file.rglob(f"{prefix}_*.csv"))
    empty = pd.DataFrame(columns=list(model.expected_columns()))
    if not input_files:
        return empty

    records = []
    for input_file in input_files:
        start, end = extract_period(input_file, prefix)
        df = reader(input_file)
        df[model.PERIOD_START] = start.isoformat()
        df[model.PERIOD_END] = end.isoformat()
        df[model.FILE_DATE] = end.isoformat()
        print(f"PLIK:{input_file} {len(df):>4} rekord/ów (DEGIRO {prefix})")
        records.append(df)

    result = pd.concat(records, ignore_index=True)
    model.check_structure(result)
    return result


def _normalize_portfolio(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in (
        DegiroPortfolioFile.QUANTITY,
        DegiroPortfolioFile.PRICE,
        DegiroPortfolioFile.LOCAL_VALUE,
        DegiroPortfolioFile.VALUE_EUR,
    ):
        if col in out.columns:
            out[col] = out[col].map(parse_degiro_number)
    for col in DegiroPortfolioFile.expected_columns():
        if col not in out.columns:
            out[col] = ""
    return out[list(DegiroPortfolioFile.expected_columns() - {
        DegiroPortfolioFile.FILE_DATE,
        DegiroPortfolioFile.PERIOD_START,
        DegiroPortfolioFile.PERIOD_END,
    })]


def _normalize_transactions(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in (
        DegiroTransactionsFile.QUANTITY,
        DegiroTransactionsFile.PRICE,
        DegiroTransactionsFile.LOCAL_VALUE,
        DegiroTransactionsFile.VALUE_EUR,
        DegiroTransactionsFile.FX_RATE,
        DegiroTransactionsFile.AUTOFX_FEE,
        DegiroTransactionsFile.DEGIRO_FEE,
        DegiroTransactionsFile.TOTAL_EUR,
    ):
        if col in out.columns:
            out[col] = out[col].map(parse_degiro_number)
    for col in DegiroTransactionsFile.expected_columns():
        if col not in out.columns:
            out[col] = ""
    return out[list(DegiroTransactionsFile.expected_columns() - {
        DegiroTransactionsFile.FILE_DATE,
        DegiroTransactionsFile.PERIOD_START,
        DegiroTransactionsFile.PERIOD_END,
    })]


def _normalize_account(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in (DegiroAccountFile.RATE, DegiroAccountFile.CHANGE, DegiroAccountFile.BALANCE):
        if col in out.columns:
            out[col] = out[col].map(parse_degiro_number)
    for col in DegiroAccountFile.expected_columns():
        if col not in out.columns:
            out[col] = ""
    return out[list(DegiroAccountFile.expected_columns() - {
        DegiroAccountFile.FILE_DATE,
        DegiroAccountFile.PERIOD_START,
        DegiroAccountFile.PERIOD_END,
    })]


def _named_periods(source_dir: Path, prefix: str) -> list[tuple[date, date]]:
    return [extract_period(path, prefix) for path in sorted(source_dir.rglob(f"{prefix}_*.csv"))]


def _sort_by_date(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    out = df.copy()
    out["_sort"] = out[date_col].map(parse_degiro_date)
    out = out.sort_values("_sort").drop(columns=["_sort"]).reset_index(drop=True)
    return out
