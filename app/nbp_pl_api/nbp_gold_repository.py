# -*- coding: utf-8 -*-
"""Cache cen złota NBP przez DATA_STEP: nbp/cenyzlota/{as_of}.parquet."""
from __future__ import annotations

from datetime import date

import pandas as pd

from data_step.data_step import DATA_STEP
from data_step.data_strep_data_types import REFRESHED
from nbp_pl_api.nbp_gold_fetch import (
    NBP_GOLD_DATE,
    NBP_GOLD_HISTORY_START,
    NBP_GOLD_PRICE,
    fetch_nbp_gold,
)

NBP_GOLD_STEP = "nbp/cenyzlota"


def nbp_gold_resource(as_of: date) -> str:
    return f"{NBP_GOLD_STEP}/{as_of:%Y-%m-%d}.parquet"


def load_nbp_gold(as_of: date | None = None) -> pd.DataFrame:
    """Pełna seria do as_of włącznie. Kolejny dzień kasuje starszy plik."""
    as_of = as_of or date.today()
    product = nbp_gold_resource(as_of)
    result = DATA_STEP.obtain(product, _collect_nbp_gold, as_of=as_of.isoformat())
    if result.get_status() == REFRESHED:
        _delete_outdated_as_of(as_of)
    return _normalize_gold_frame(result.data_frame())


def gold_price_as_of(
    valuation_date: date,
    series: pd.DataFrame | None = None,
) -> tuple[date, float]:
    """Ostatnia publikacja NBP ≤ valuation_date: (data, PLN za gram)."""
    frame = _normalize_gold_frame(series) if series is not None else load_nbp_gold(valuation_date)
    if frame.empty:
        raise ValueError(f"Brak cen złota NBP na {valuation_date.isoformat()}.")

    published = pd.to_datetime(frame[NBP_GOLD_DATE]).dt.normalize()
    target = pd.Timestamp(valuation_date).normalize()
    eligible = frame.loc[published <= target]
    if eligible.empty:
        raise ValueError(
            f"Brak ceny złota NBP na dzień {valuation_date.isoformat()} ani wcześniej."
        )
    row = eligible.iloc[-1]
    price_day = pd.Timestamp(row[NBP_GOLD_DATE]).date()
    price = float(row[NBP_GOLD_PRICE])
    if pd.isna(price):
        raise ValueError(f"Pusta cena złota NBP na {price_day.isoformat()}.")
    return price_day, price


def _collect_nbp_gold(as_of: str, **_kwargs) -> pd.DataFrame:
    end = date.fromisoformat(as_of)
    if end < NBP_GOLD_HISTORY_START:
        raise ValueError(
            f"Ceny złota NBP są dostępne od {NBP_GOLD_HISTORY_START.isoformat()}, nie od {as_of}."
        )
    return fetch_nbp_gold(NBP_GOLD_HISTORY_START, end)


def _normalize_gold_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=[NBP_GOLD_DATE, NBP_GOLD_PRICE])
    out = frame.copy()
    out[NBP_GOLD_DATE] = pd.to_datetime(out[NBP_GOLD_DATE]).dt.normalize()
    out[NBP_GOLD_PRICE] = pd.to_numeric(out[NBP_GOLD_PRICE], errors="coerce")
    out = out.dropna(subset=[NBP_GOLD_DATE])
    out = out.sort_values(NBP_GOLD_DATE).reset_index(drop=True)
    return out[[NBP_GOLD_DATE, NBP_GOLD_PRICE]]


def _delete_outdated_as_of(keep_as_of: date) -> None:
    keep = nbp_gold_resource(keep_as_of)
    keep_path = DATA_STEP.get_absolute_file_path(keep)
    folder = keep_path.parent
    if not folder.is_dir():
        return
    stale: list[str] = []
    for path in folder.glob("*.parquet"):
        if path.name == keep_path.name:
            continue
        path.unlink(missing_ok=True)
        stale.append(f"{NBP_GOLD_STEP}/{path.stem}.parquet")
    if stale:
        DATA_STEP.metadata.delete_many(stale)
