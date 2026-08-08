# -*- coding: utf-8 -*-
"""Parser polskich wyciągów Revolut savings-statement_*.csv."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pandas as pd

from importers.revolut.account_data_model import RevolutAccountFile
from importers.revolut.deposit_data_model import RevolutDepositFile

SAVINGS_STATEMENT_PREFIX = "savings-statement"
REVOLUT_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

COL_DATA = "Data"
COL_OPIS = "Opis"
COL_WYPLATA = "Wypłata pieniędzy"
COL_WPLYWY = "Wpływy"
COL_SALDO = "Saldo"

OPIS_DEPOSIT = "Depozyt"
OPIS_INTEREST = "Oprocentowanie brutto"
OPIS_WITHDRAWAL = "Wypłata"

PERIOD_START = "period_start"
PERIOD_END = "period_end"

_PL_MONTHS = {
    "sty": 1,
    "lut": 2,
    "mar": 3,
    "kwi": 4,
    "maj": 5,
    "cze": 6,
    "lip": 7,
    "sie": 8,
    "wrz": 9,
    "paź": 10,
    "paz": 10,
    "lis": 11,
    "gru": 12,
}

_AMOUNT_TOKEN_RE = re.compile(
    r"(?P<num>[\d\s\u00a0]+,\d{2})\s*(?P<cur>PLN|€|EUR)|"
    r"(?P<cur2>€|EUR)\s*(?P<num2>[\d\s\u00a0]+[.,]\d{2})",
    re.IGNORECASE,
)


def is_savings_statement_filename(name: str) -> bool:
    stem = Path(name).stem
    return stem.split("_")[0] == SAVINGS_STATEMENT_PREFIX


def parse_savings_period(path: Path) -> tuple[date, date]:
    """savings-statement_{od}_{do}_pl-pl_{kod1}_{kod2}.csv"""
    parts = path.stem.split("_")
    if parts[0] != SAVINGS_STATEMENT_PREFIX or len(parts) < 3:
        raise ValueError(f"Unexpected savings statement name: {path.name}")
    start_s, end_s = parts[1], parts[2]
    if not REVOLUT_DATE_PATTERN.match(start_s) or not REVOLUT_DATE_PATTERN.match(end_s):
        raise ValueError(f"Unexpected period in {path.name}: {start_s}..{end_s}")
    return date.fromisoformat(start_s), date.fromisoformat(end_s)


def detect_savings_currency(df: pd.DataFrame) -> str:
    """Waluta z treści kwot (PLN / €) — nie z nazwy pliku."""
    amount_cols = [c for c in (COL_WYPLATA, COL_WPLYWY, COL_SALDO) if c in df.columns]
    if not amount_cols:
        raise ValueError("Brak kolumn kwot w savings-statement")

    saw_pln = False
    saw_eur = False
    for col in amount_cols:
        for raw in df[col].dropna().astype(str):
            text = raw.replace("\u00a0", " ").strip()
            if not text:
                continue
            if "PLN" in text.upper():
                saw_pln = True
            if "€" in text or re.search(r"\bEUR\b", text, re.IGNORECASE):
                saw_eur = True

    if saw_pln and saw_eur:
        raise ValueError("Mieszane waluty PLN/EUR w jednym savings-statement")
    if saw_pln:
        return "pln"
    if saw_eur:
        return "eur"
    raise ValueError("Nie wykryto waluty PLN ani EUR w savings-statement")


def parse_pl_amount(value) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).replace("\u00a0", " ").strip()
    if not text or text.lower() == "nan":
        return None

    m = _AMOUNT_TOKEN_RE.search(text)
    if m:
        num = m.group("num") or m.group("num2")
    else:
        num = re.sub(r"[^\d,.\-]", "", text)
    if not num:
        return None
    num = num.replace(" ", "").replace(".", "").replace(",", ".")
    return float(num)


def parse_pl_date(value) -> str:
    """'20 sie 2025' / '1 sty 2026' → YYYY-MM-DD."""
    text = str(value).replace("\u00a0", " ").strip()
    parts = text.split()
    if len(parts) != 3:
        raise ValueError(f"Unexpected PL date: {value!r}")
    day_s, month_s, year_s = parts
    month = _PL_MONTHS.get(month_s.lower())
    if month is None:
        raise ValueError(f"Unknown PL month in date: {value!r}")
    return date(int(year_s), month, int(day_s)).isoformat()


def normalize_savings_statement(
    raw: pd.DataFrame,
    *,
    period_start: date,
    period_end: date,
) -> pd.DataFrame:
    required = {COL_DATA, COL_OPIS, COL_WYPLATA, COL_WPLYWY, COL_SALDO}
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"Brak kolumn w savings-statement: {sorted(missing)}")

    currency = detect_savings_currency(raw)
    rows: list[dict] = []
    for _, row in raw.iterrows():
        money_out = parse_pl_amount(row[COL_WYPLATA])
        money_in = parse_pl_amount(row[COL_WPLYWY])
        balance = parse_pl_amount(row[COL_SALDO])
        if balance is None:
            continue
        rows.append(
            {
                RevolutDepositFile.COMPLETED_DATE: str(row[COL_DATA]),
                RevolutDepositFile.PRODUCT_NAME: "",
                RevolutDepositFile.DESCRIPTION: str(row[COL_OPIS]).strip(),
                RevolutDepositFile.MONEY_OUT: money_out if money_out is not None else float("nan"),
                RevolutDepositFile.MONEY_IN: money_in if money_in is not None else float("nan"),
                RevolutDepositFile.DEP_BALANCE: str(row[COL_SALDO]),
                RevolutDepositFile.DATE: parse_pl_date(row[COL_DATA]),
                RevolutDepositFile.BALANCE: float(balance),
                RevolutDepositFile.CURRENCY: currency,
                RevolutDepositFile.FILE_DATE: "",
                PERIOD_START: period_start.isoformat(),
                PERIOD_END: period_end.isoformat(),
            }
        )

    if not rows:
        return empty_savings_frame()

    result = pd.DataFrame(rows)
    result = result.reindex(columns=_deposit_column_order())
    return result.sort_values(by=[RevolutDepositFile.DATE]).reset_index(drop=True)


def _deposit_column_order() -> list[str]:
    # Stabilna kolejność — expected_columns() to set.
    return [
        RevolutDepositFile.COMPLETED_DATE,
        RevolutDepositFile.PRODUCT_NAME,
        RevolutDepositFile.DESCRIPTION,
        RevolutDepositFile.MONEY_OUT,
        RevolutDepositFile.MONEY_IN,
        RevolutDepositFile.DEP_BALANCE,
        RevolutDepositFile.DATE,
        RevolutDepositFile.BALANCE,
        RevolutDepositFile.CURRENCY,
        RevolutDepositFile.FILE_DATE,
        RevolutDepositFile.PERIOD_START,
        RevolutDepositFile.PERIOD_END,
    ]


def empty_savings_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=_deposit_column_order())


def assert_no_coverage_gaps(periods: list[tuple[date, date]], *, asset_id: str = "") -> None:
    """Po posortowaniu okresów: next.start > prev.end + 1 day → twardy błąd."""
    from importers.period_coverage import assert_no_coverage_gaps as _assert_gaps

    _assert_gaps(periods, asset_id=asset_id, label="savings-statement")


def savings_unique_key() -> list[str]:
    return [
        RevolutDepositFile.DATE,
        RevolutDepositFile.DESCRIPTION,
        RevolutDepositFile.BALANCE,
        RevolutDepositFile.MONEY_OUT,
        RevolutDepositFile.MONEY_IN,
    ]
