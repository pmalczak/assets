# -*- coding: utf-8 -*-
from __future__ import annotations

__author__ = "pmalczak@gmail.com"

import csv
import re
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from data_step.data_step import DATA_STEP
from importers.deduplicate_records import deduplicate_records
from importers.revolut.trading_data_model import RevolutTradingFile, RevolutTradingPnlFile

REVOLUT_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TRADING_PREFIX = "trading-account-statement"
_PNL_PREFIX = "trading-pnl-statement"


def read_revolut_trading_transactions(input_path: Path, asset_id: str) -> tuple[pd.DataFrame, list[str]]:
    resource = f"01 source/{asset_id}-trading.parquet"
    r = DATA_STEP.obtain_dependent(resource, _read_revolut_trading_transactions, input_path)
    df = r.data_frame()
    warnings = period_gap_warnings(
        named_periods_from_dir(input_path, _TRADING_PREFIX), label=_TRADING_PREFIX
    )
    return df, warnings


def read_revolut_trading_pnl(input_path: Path, asset_id: str) -> tuple[pd.DataFrame, list[str]]:
    resource = f"01 source/{asset_id}-pnl.parquet"
    r = DATA_STEP.obtain_dependent(resource, _read_revolut_trading_pnl, input_path)
    df = r.data_frame()
    warnings = period_gap_warnings(
        named_periods_from_dir(input_path, _PNL_PREFIX), label=_PNL_PREFIX
    )
    return df, warnings


def named_periods_from_dir(source_dir: Path, prefix: str) -> list[tuple[str, str]]:
    periods = []
    for path in sorted(source_dir.rglob(f"{prefix}_*.csv")):
        periods.append(extract_statement_period(path, prefix))
    return periods


def _read_revolut_trading_transactions(source_file: Path = None) -> pd.DataFrame:
    input_files = sorted(source_file.rglob(f"{_TRADING_PREFIX}_*.csv"))
    empty = pd.DataFrame(columns=list(RevolutTradingFile.expected_columns()))
    if not input_files:
        return empty

    periods = []
    records = []
    for input_file in input_files:
        start, end = extract_statement_period(input_file, _TRADING_PREFIX)
        periods.append((start, end))
        df = pd.read_csv(input_file)
        df[RevolutTradingFile.PERIOD_START] = start
        df[RevolutTradingFile.PERIOD_END] = end
        df[RevolutTradingFile.FILE_DATE] = end
        print(f"PLIK:{input_file} {len(df):>4} rekord/ów")
        records.append(df)

    result = _merge_dedupe(records, RevolutTradingFile.DATE, RevolutTradingFile.unique_key())
    result[RevolutTradingFile.FILE_DATE] = max(p[1] for p in periods)
    result = normalize_trading_transactions(result)
    RevolutTradingFile.check_structure(result)
    return result


def _read_revolut_trading_pnl(source_file: Path = None) -> pd.DataFrame:
    input_files = sorted(source_file.rglob(f"{_PNL_PREFIX}_*.csv"))
    empty = pd.DataFrame(columns=list(RevolutTradingPnlFile.expected_columns()))
    if not input_files:
        return empty

    periods = []
    records = []
    for input_file in input_files:
        start, end = extract_statement_period(input_file, _PNL_PREFIX)
        periods.append((start, end))
        df = parse_trading_pnl_csv(input_file)
        df[RevolutTradingPnlFile.PERIOD_START] = start
        df[RevolutTradingPnlFile.PERIOD_END] = end
        df[RevolutTradingPnlFile.FILE_DATE] = end
        print(f"PLIK:{input_file} {len(df):>4} rekord/ów PnL")
        records.append(df)

    # PnL rows may use Date or Date sold for chronology
    date_col = "_sort_date"
    prepared = []
    for df in records:
        work = df.copy()
        sold = pd.to_datetime(work[RevolutTradingPnlFile.DATE_SOLD], errors="coerce")
        other = pd.to_datetime(work[RevolutTradingPnlFile.DATE], errors="coerce")
        work[date_col] = sold.fillna(other)
        prepared.append(work)

    result = _merge_dedupe(prepared, date_col, RevolutTradingPnlFile.unique_key())
    if date_col in result.columns:
        result = result.drop(columns=[date_col])
    result[RevolutTradingPnlFile.FILE_DATE] = max(p[1] for p in periods)
    RevolutTradingPnlFile.check_structure(result)
    return result


def _merge_dedupe(records: list[pd.DataFrame], date_col: str, key_cols: list[str]) -> pd.DataFrame:
    result = None
    for record in records:
        if result is None:
            result = record
            continue
        result = deduplicate_records(result, record, date_col, key_cols)
    return result if result is not None else pd.DataFrame()


def parse_trading_amount(value) -> float | None:
    """Tekst typu 'EUR 67.86' / 'EUR 125' → float; już liczbowe zostaw."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return None
    s = s.replace(",", "")
    s = re.sub(r"[^\d.\-]", "", s)
    if s in ("", "-", ".", "-."):
        return None
    return float(s)


def invert_fx_rate(value, ndigits: int = 4) -> float | None:
    fx = parse_trading_amount(value)
    if fx is None or fx == 0:
        return None
    return round(1.0 / fx, ndigits)


def normalize_trading_transactions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Przekształcenia blottera po merge:
    - SELL - MARKET: Quantity *= -1
    - BUY - MARKET: Total Amount *= -1
    - Price per share / Total Amount: usuń walutę → float
    - FX Rate: 1/fx zaokrąglone do 4 miejsc
    """
    if df is None or df.empty:
        return df.copy() if df is not None else pd.DataFrame()

    out = df.copy()
    sell = out[RevolutTradingFile.TYPE] == RevolutTradingFile.TYPE_SELL
    buy = out[RevolutTradingFile.TYPE] == RevolutTradingFile.TYPE_BUY
    qty = pd.to_numeric(out[RevolutTradingFile.QUANTITY], errors="coerce")
    out.loc[sell, RevolutTradingFile.QUANTITY] = -qty.loc[sell].abs()

    out[RevolutTradingFile.PRICE_PER_SHARE] = out[RevolutTradingFile.PRICE_PER_SHARE].map(
        parse_trading_amount
    )
    out[RevolutTradingFile.TOTAL_AMOUNT] = out[RevolutTradingFile.TOTAL_AMOUNT].map(
        parse_trading_amount
    )
    total = pd.to_numeric(out[RevolutTradingFile.TOTAL_AMOUNT], errors="coerce")
    out.loc[buy, RevolutTradingFile.TOTAL_AMOUNT] = -total.loc[buy].abs()
    out[RevolutTradingFile.FX_RATE] = out[RevolutTradingFile.FX_RATE].map(invert_fx_rate)
    return out


def extract_statement_period(input_file: Path, prefix: str) -> tuple[str, str]:
    parts = Path(input_file).stem.split("_")
    if parts[0] != prefix or len(parts) < 3:
        raise ValueError(f"Unexpected Revolut trading statement name: {input_file.name}")
    start, end = parts[1], parts[2]
    if not REVOLUT_DATE_PATTERN.match(start):
        raise ValueError(f"Unexpected start date in {input_file.name}: {start}")
    if not REVOLUT_DATE_PATTERN.match(end):
        raise ValueError(f"Unexpected end date in {input_file.name}: {end}")
    return start, end


def period_gap_warnings(periods: list[tuple[str, str]], label: str) -> list[str]:
    if not periods:
        return []
    parsed = sorted((date.fromisoformat(a), date.fromisoformat(b)) for a, b in periods)
    merged: list[list[date]] = [[parsed[0][0], parsed[0][1]]]
    for start, end in parsed[1:]:
        if start <= merged[-1][1] + timedelta(days=1):
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    warnings = []
    for i in range(len(merged) - 1):
        gap_start = merged[i][1] + timedelta(days=1)
        gap_end = merged[i + 1][0] - timedelta(days=1)
        if gap_start <= gap_end:
            warnings.append(
                f"Luka w okresach {label}: {gap_start.isoformat()} … {gap_end.isoformat()} "
                f"— możliwa utrata danych"
            )
    return warnings


def parse_trading_pnl_csv(path: Path) -> pd.DataFrame:
    text = path.read_text(encoding="utf-8-sig")
    section = None
    header = None
    rows: list[dict] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line in (RevolutTradingPnlFile.SECTION_SELLS, RevolutTradingPnlFile.SECTION_OTHER):
            section = line
            header = None
            continue
        if section is None:
            continue
        if header is None:
            header = next(csv.reader([line]))
            continue
        values = next(csv.reader([line]))
        if len(values) != len(header):
            # pad / trim defensively
            if len(values) < len(header):
                values = values + [""] * (len(header) - len(values))
            else:
                values = values[: len(header)]
        row = dict(zip(header, values))
        row[RevolutTradingPnlFile.SECTION] = section
        rows.append(row)

    cols = list(RevolutTradingPnlFile.expected_columns() - {
        RevolutTradingPnlFile.FILE_DATE,
        RevolutTradingPnlFile.PERIOD_START,
        RevolutTradingPnlFile.PERIOD_END,
    })
    if not rows:
        return pd.DataFrame(columns=cols)

    df = pd.DataFrame(rows)
    for col in cols:
        if col not in df.columns:
            df[col] = ""
    return df[cols]


def isin_by_symbol(pnl_df: pd.DataFrame) -> dict[str, str]:
    if pnl_df is None or pnl_df.empty:
        return {}
    result: dict[str, str] = {}
    for _, row in pnl_df.iterrows():
        symbol = str(row.get(RevolutTradingPnlFile.SYMBOL) or "").strip()
        isin = str(row.get(RevolutTradingPnlFile.ISIN) or "").strip()
        if symbol and re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}\d", isin):
            result[symbol] = isin
    return result
