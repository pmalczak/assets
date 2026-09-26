# -*- coding: utf-8 -*-
"""Przeliczanie CF na PLN kursem NBP z dnia transakcji."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache

import pandas as pd

from fx.get_last_fx import get_fx_as_of
from fx.data_model import LastFx
from importers.assets.data_model import AssetsDef
from nbp_fx_repo.nbp_fx_repository import NBP_API_EUR, NBP_API_PLN, NbpFxRepository


@dataclass(frozen=True)
class PlnConversion:
    amount_pln: float
    fx_rate: float
    fx_date: str


def to_pln(
    amount: float,
    currency: str,
    on_date: date,
    *,
    fx_rates: pd.DataFrame | None = None,
) -> PlnConversion:
    """Kwota × kurs NBP (ostatni ≤ on_date). PLN → rate 1.0."""
    code = str(currency or "").strip().upper()
    if code in {"", NBP_API_PLN, "PLN"}:
        return PlnConversion(amount_pln=float(amount), fx_rate=1.0, fx_date=on_date.isoformat())
    if code != NBP_API_EUR:
        raise ValueError(f"Nieobsługiwana waluta CF: {currency!r} (v1: PLN/EUR)")

    rates = fx_rates if fx_rates is not None else _default_fx_rates()
    row = get_fx_as_of(rates, on_date)
    eur = row.loc[row[AssetsDef.CURRENCY] == NBP_API_EUR]
    if eur.empty:
        raise ValueError(f"Brak kursu EUR/PLN na {on_date.isoformat()}")
    rate = float(eur.iloc[0][LastFx.FX])
    fx_date = str(eur.iloc[0][AssetsDef.VALUE_DATE])
    return PlnConversion(amount_pln=float(amount) * rate, fx_rate=rate, fx_date=fx_date)


@lru_cache(maxsize=1)
def _default_fx_rates() -> pd.DataFrame:
    from app_proc.data_steps_root import get_nbp_fx_cache_dir

    repo = NbpFxRepository(target_directory=get_nbp_fx_cache_dir(), min_year=2005)
    rates = repo.update_to_date()
    return rates[[NBP_API_EUR]].copy()


def clear_fx_cache() -> None:
    _default_fx_rates.cache_clear()
