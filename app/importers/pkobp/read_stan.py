# -*- coding: utf-8 -*-
"""Stan rachunku rejestrowego PKO BP (obligacje skarbowe)."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pandas as pd

from data_step.data_step import DATA_STEP
from importers.pkobp.data_model import PkoBpStan

_STAN_NAME_RE = re.compile(
    r"^StanRachunkuRejestrowego_(?P<file_date>\d{4}-\d{2}-\d{2})\.xls$",
    re.IGNORECASE,
)


def read_obligacje_stan(input_path: Path, asset_id: str) -> pd.DataFrame:
    resource = f"01 source/{asset_id}-stan.parquet"
    r = DATA_STEP.obtain_dependent(resource, import_stan_files, input_path)
    return r.data_frame()


def import_stan_files(source_file: Path = None) -> pd.DataFrame:
    assert source_file is not None and source_file.is_dir()
    files = sorted(source_file.glob("StanRachunkuRejestrowego_*.xls"))
    empty = pd.DataFrame(columns=list(PkoBpStan.expected_columns()))
    if not files:
        return empty

    frames = []
    for path in files:
        file_date = stan_file_date(path)
        if file_date is None:
            continue
        df = pd.read_excel(path)
        missing = PkoBpStan.source_columns() - set(df.columns)
        if missing:
            raise ValueError(f"Brak kolumn w {path.name}: {missing}")
        out = df.loc[:, list(PkoBpStan.source_columns())].copy()
        out[PkoBpStan.FILE_DATE] = file_date.isoformat()
        out = add_unit_price(out)
        print(f"PLIK:{path} {len(out):>4} rekord/ów")
        frames.append(out)

    if not frames:
        return empty
    result = pd.concat(frames, ignore_index=True)
    PkoBpStan.check_structure(result)
    return result


def stan_file_date(path: Path) -> date | None:
    match = _STAN_NAME_RE.fullmatch(path.name)
    if not match:
        return None
    return date.fromisoformat(match.group("file_date"))


def add_unit_price(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    available = pd.to_numeric(out[PkoBpStan.QTY_AVAILABLE], errors="coerce").fillna(0.0)
    blocked = pd.to_numeric(out[PkoBpStan.QTY_BLOCKED], errors="coerce").fillna(0.0)
    qty = available + blocked
    value = pd.to_numeric(out[PkoBpStan.CURRENT_VALUE], errors="coerce")
    unit = pd.Series(pd.NA, index=out.index, dtype="Float64")
    mask = qty > 0
    unit.loc[mask] = (value.loc[mask] / qty.loc[mask]).round(6)
    out[PkoBpStan.UNIT_PRICE] = unit
    return out


def select_stan_as_of(stan_df: pd.DataFrame, valuation_date: date) -> pd.DataFrame:
    """Wiersze z najnowszego pliku stanu z FILE_DATE ≤ valuation_date."""
    if stan_df is None or stan_df.empty:
        return pd.DataFrame(columns=list(PkoBpStan.expected_columns()))

    work = stan_df.copy()
    work["_fd"] = pd.to_datetime(work[PkoBpStan.FILE_DATE], errors="coerce")
    cutoff = pd.Timestamp(valuation_date)
    work = work.loc[work["_fd"].notna() & (work["_fd"] <= cutoff)]
    if work.empty:
        return pd.DataFrame(columns=list(PkoBpStan.expected_columns()))

    latest = work["_fd"].max()
    result = work.loc[work["_fd"] == latest].drop(columns=["_fd"])
    return result.reset_index(drop=True)


def stan_mtm_total(stan_as_of: pd.DataFrame) -> float:
    if stan_as_of is None or stan_as_of.empty:
        return 0.0
    return float(pd.to_numeric(stan_as_of[PkoBpStan.CURRENT_VALUE], errors="coerce").fillna(0.0).sum())
