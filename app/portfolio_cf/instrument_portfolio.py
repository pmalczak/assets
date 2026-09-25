# -*- coding: utf-8 -*-
"""Mapowanie instrument_id → nazwany portfel (konfiguracja startowa = stan obecny)."""
from __future__ import annotations

from portfolios.assignment import (
    PORTFOLIO_DLUGOTERMINOWY,
    PORTFOLIO_DLUGOTERMINOWY_ASSET_IDS,
    PORTFOLIO_GM,
    PORTFOLIO_NIERUCHOMOSCI,
    PORTFOLIO_PLYNNY,
    PORTFOLIO_REVOLUT_ROBO,
    portfolio_for_asset_id,
)

# Prefiksy kont brokerskich → portfel (tickery + CASH).
_BROKER_PREFIX_PORTFOLIO: tuple[tuple[str, str], ...] = (
    ("p_re_robo:", PORTFOLIO_REVOLUT_ROBO),
    ("p_degiro:", PORTFOLIO_GM),
    ("p_xtb:", PORTFOLIO_GM),
)

# Id nieruchomości z katalogu ROI (także sprzedane poza snapshotem).
_PROPERTY_INSTRUMENT_IDS = frozenset(
    {
        "aquamarina",
        "garaz",
        "karpacz",
        "kiemliczow_1",
        "kiemliczow_3",
        "kiemliczow_4",
        "opoczynska",
        "starogajowa",
        "horbaczewskiego",
        "rumiankowa",
    }
)

# XIRR v1: cash pool poza zakresem.
XIRR_EXCLUDED_PORTFOLIO = "0 CASH-POOL"


def portfolio_for_instrument(instrument_id: str | None) -> str:
    """Portfel nazwanego instrumentu (nie kontenera brokera jako blob)."""
    key = str(instrument_id or "").strip()
    if not key:
        return PORTFOLIO_PLYNNY

    for prefix, portfolio in _BROKER_PREFIX_PORTFOLIO:
        if key.startswith(prefix):
            return portfolio

    if key in _PROPERTY_INSTRUMENT_IDS:
        return PORTFOLIO_NIERUCHOMOSCI

    if key in PORTFOLIO_DLUGOTERMINOWY_ASSET_IDS:
        return PORTFOLIO_DLUGOTERMINOWY

    # Emisje obligacji / depozyty: kontener lub prefix kontenera.
    if key.startswith("obligacjeskarbowe:"):
        return PORTFOLIO_PLYNNY

    # Pojedyncze id katalogu / kontenera — jak assignment.py
    if ":" not in key:
        return portfolio_for_asset_id(key)

    # np. p_re_eur:… depozyty — reszta inwestycji → Płynny
    return PORTFOLIO_PLYNNY


def is_xirr_excluded_instrument(instrument_id: str | None, *, typ: str | None = None) -> bool:
    kind = str(typ or "").strip()
    if kind.startswith("cash_pool."):
        return True
    return False
