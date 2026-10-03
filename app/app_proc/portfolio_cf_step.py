# -*- coding: utf-8 -*-
"""Kanoniczna ścieżka DATA_STEP dla portfolio_cf + venue ROI (dawniej ``10 roi``).

W osobnym module (nie ``portfolio_cf.*``), żeby ``roi_products`` nie ładował
``portfolio_cf.__init__`` i nie domykał cyklicznego importu ze snapshotami.
"""
from __future__ import annotations

from datetime import date

PORTFOLIO_CF_STEP = "11 portfolio_cf"
# Bump przy zmianie semantyki ledgera / XIRR / katalogu ROI — stare parquet nieaktualne.
PORTFOLIO_CF_SCHEMA = 6

# Dawny osobny produkt — całe drzewo do usunięcia przez prune_stale_data_steps.
OBSOLETE_DATA_STEP_PRODUCTS = ("10 roi",)


def portfolio_cf_prefix(valuation_date: date) -> str:
    """``11 portfolio_cf/{date}/s{N}`` — wspólny prefix ledger / coverage / XIRR / catalog ROI."""
    return (
        f"{PORTFOLIO_CF_STEP}/{valuation_date:%Y-%m-%d}/"
        f"s{PORTFOLIO_CF_SCHEMA}"
    )
