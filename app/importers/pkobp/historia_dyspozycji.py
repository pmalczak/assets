# -*- coding: utf-8 -*-
"""Nazewnictwo i wybór pliku HistoriaDyspozycji (PKO BP)."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pandas as pd

from importers.pkobp.data_model import PkoBpBonds

HISTORIA_DYSPOZYCJI_FILE = "HistoriaDyspozycji.xls"

_HISTORIA_DATED_RE = re.compile(
    rf"^(?P<first>\d{{4}}-\d{{2}}-\d{{2}}) (?P<last>\d{{4}}-\d{{2}}-\d{{2}}) {re.escape(HISTORIA_DYSPOZYCJI_FILE)}$",
    re.IGNORECASE,
)

_COMPARE_COLS = [
    PkoBpBonds.DATE,
    PkoBpBonds.ORDER_TYPE,
    PkoBpBonds.CODE,
    PkoBpBonds.NO_LINE,
    PkoBpBonds.SERIES,
    PkoBpBonds.BONDS_NO,
    PkoBpBonds.AMOUNT,
    PkoBpBonds.STAT,
    PkoBpBonds.NOTES,
]


def dated_historia_filename(first: date, last: date) -> str:
    return f"{first:%Y-%m-%d} {last:%Y-%m-%d} {HISTORIA_DYSPOZYCJI_FILE}"


def read_historia_excel(path: Path) -> pd.DataFrame:
    return pd.read_excel(path)


def disposition_date_range_from_df(df: pd.DataFrame) -> tuple[date, date]:
    if PkoBpBonds.DATE not in df.columns:
        raise ValueError(f"Brak kolumny {PkoBpBonds.DATE!r}")
    dates = pd.to_datetime(df[PkoBpBonds.DATE], errors="coerce").dropna()
    if dates.empty:
        raise ValueError("Brak dat dyspozycji")
    return dates.min().date(), dates.max().date()


def disposition_date_range(path: Path) -> tuple[date, date]:
    """Pierwsza i ostatnia DATA DYSPOZYCJI z pliku Excel."""
    return disposition_date_range_from_df(read_historia_excel(path))


def dated_historia_filename_from_df(df: pd.DataFrame) -> str:
    first, last = disposition_date_range_from_df(df)
    return dated_historia_filename(first, last)


def dated_historia_filename_from_excel(path: Path) -> str:
    return dated_historia_filename_from_df(read_historia_excel(path))


def list_historia_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        p
        for p in directory.iterdir()
        if p.is_file() and p.name.lower().endswith(HISTORIA_DYSPOZYCJI_FILE.lower())
    )


def resolve_historia_file(directory: Path) -> Path:
    """Wybiera plik historii dyspozycji — preferuje najnowszą datę końcową w nazwie."""
    candidates = list_historia_files(directory)
    if not candidates:
        raise FileNotFoundError(directory / HISTORIA_DYSPOZYCJI_FILE)
    return max(candidates, key=_historia_sort_key)


def historia_contains_all(container: pd.DataFrame, candidate: pd.DataFrame) -> bool:
    """Czy `container` zawiera wszystkie transakcje z `candidate`."""
    left = _normalize_historia_rows(container)
    right = _normalize_historia_rows(candidate)
    if right.empty:
        return True
    if left.empty:
        return False
    merged = right.merge(left, on=_COMPARE_COLS, how="left", indicator=True)
    return bool((merged["_merge"] == "both").all())


def find_covering_historia(directory: Path, candidate: pd.DataFrame) -> Path | None:
    """Pierwszy plik w katalogu, który już zawiera wszystkie transakcje z `candidate`."""
    for path in list_historia_files(directory):
        existing = read_historia_excel(path)
        if historia_contains_all(existing, candidate):
            return path
    return None


def _normalize_historia_rows(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in _COMPARE_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Brak kolumn w historii dyspozycji: {missing}")
    out = df.loc[:, _COMPARE_COLS].copy()
    out[PkoBpBonds.DATE] = pd.to_datetime(out[PkoBpBonds.DATE], errors="coerce").dt.normalize()
    out[PkoBpBonds.ORDER_TYPE] = out[PkoBpBonds.ORDER_TYPE].astype("string").str.strip()
    out[PkoBpBonds.CODE] = out[PkoBpBonds.CODE].astype("string").str.strip()
    out[PkoBpBonds.SERIES] = out[PkoBpBonds.SERIES].astype("string").fillna("").str.strip()
    out[PkoBpBonds.STAT] = out[PkoBpBonds.STAT].astype("string").str.strip()
    out[PkoBpBonds.NOTES] = out[PkoBpBonds.NOTES].astype("string").fillna("").str.strip()
    out[PkoBpBonds.NO_LINE] = pd.to_numeric(out[PkoBpBonds.NO_LINE], errors="coerce")
    out[PkoBpBonds.BONDS_NO] = pd.to_numeric(out[PkoBpBonds.BONDS_NO], errors="coerce")
    out[PkoBpBonds.AMOUNT] = pd.to_numeric(out[PkoBpBonds.AMOUNT], errors="coerce").round(2)
    out = out.dropna(subset=[PkoBpBonds.DATE, PkoBpBonds.NO_LINE])
    return out.drop_duplicates()


def _historia_sort_key(path: Path) -> tuple[str, str, float]:
    match = _HISTORIA_DATED_RE.fullmatch(path.name)
    if match:
        return match.group("last"), match.group("first"), path.stat().st_mtime
    return "0001-01-01", "0001-01-01", path.stat().st_mtime
