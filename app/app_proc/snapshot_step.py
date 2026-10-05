# -*- coding: utf-8 -*-
"""Kanoniczna ścieżka DATA_STEP: snapshot katalogu + ledger/XIRR/ROI.

W osobnym module (nie ``calculate_assets`` / ``portfolio_cf.*``), żeby uniknąć
cykli importu.
"""
from __future__ import annotations

from datetime import date

SNAPSHOTS_STEP = "snapshots"
# Wspólny sN dla ``_assets`` i ledger/XIRR/ROI. Bump unieważnia całe drzewo daty.
SNAPSHOT_SCHEMA = 1
ASSETS_SNAPSHOT_FILE = "_assets.parquet"

# Dawne osobne produkty — całe drzewo wycina prune_stale_data_steps.
OBSOLETE_DATA_STEP_PRODUCTS = ("10 roi", "09 assets", "11 portfolio_cf")

# Alias historyczny (UI / importy).
ASSETS_SNAPSHOT_STEP = SNAPSHOTS_STEP
ASSETS_SNAPSHOT_SCHEMA = SNAPSHOT_SCHEMA
PORTFOLIO_CF_STEP = SNAPSHOTS_STEP
PORTFOLIO_CF_SCHEMA = SNAPSHOT_SCHEMA


def snapshot_prefix(valuation_date: date) -> str:
    """``snapshots/{date}/s{N}``."""
    return f"{SNAPSHOTS_STEP}/{valuation_date:%Y-%m-%d}/s{SNAPSHOT_SCHEMA}"


def assets_snapshot_prefix(valuation_date: date) -> str:
    return snapshot_prefix(valuation_date)


def assets_snapshot_resource(valuation_date: date) -> str:
    """``snapshots/{date}/s{N}/_assets.parquet``."""
    return f"{snapshot_prefix(valuation_date)}/{ASSETS_SNAPSHOT_FILE}"


def portfolio_cf_prefix(valuation_date: date) -> str:
    """Ten sam prefix co snapshot katalogu — ledger / coverage / XIRR / catalog ROI."""
    return snapshot_prefix(valuation_date)
