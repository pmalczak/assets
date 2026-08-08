# -*- coding: utf-8 -*-
"""Snapshot BROKER Trade Republic: 1 wiersz; na start NAV=0 (brak pozycji instrumentów)."""
from __future__ import annotations

__author__ = "pmalczak@gmail.com"

from datetime import date
from pathlib import Path

import pandas as pd

from app_proc.data_root import resolve_asset_dir
from evaluators.valuation_date import format_date_columns
from importers.assets.data_model import AssetsDef, GroupDomain, TypeDomain
from importers.traderepublic.data_model import DEFAULT_TRADEREPUBLIC_ASSET_ID
from importers.traderepublic.read_traderepublic import read_traderepublic_transactions


def is_traderepublic_broker(assets_file_row: pd.Series) -> bool:
    asset_id = str(assets_file_row.get(AssetsDef.ID, "")).strip()
    return asset_id == DEFAULT_TRADEREPUBLIC_ASSET_ID


def evaluate_broker_traderepublic(
    data_root: Path,
    asset_id: str,
    assets_file_row: pd.Series,
    valuation_date: date,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Syntetyczna wycena rachunku Trade Republic.
    Na start: brak mapowania BUY/SELL → NAV=0 (top-upy poza NAV FIFO, jak cash roboczy w robo).
    """
    p = resolve_asset_dir(asset_id, assets_file_row[AssetsDef.TYPE])
    warnings: list[str] = []
    if not p.is_dir():
        warnings.append(
            f"Brak katalogu {p} — uruchom Import wyciągów "
            f"(Eksport transakcji.csv → assets/{asset_id}/)."
        )
        blotter = pd.DataFrame()
    else:
        blotter = read_traderepublic_transactions(p, asset_id)
        if blotter.empty:
            warnings.append("Brak eksportów Trade Republic w katalogu assetu.")
        else:
            warnings.append(
                "Trade Republic: wycena pozycji instrumentów jeszcze niezaimplementowana "
                "(NAV kontenera = 0; top-up poza FIFO)."
            )

    row = AssetsDef.as_assets_row(assets_file_row)
    row[AssetsDef.VALUE] = 0.0
    row[AssetsDef.EVALUATION_DATE] = valuation_date.isoformat()
    row[AssetsDef.TYPE] = TypeDomain.EQUITIES
    row[AssetsDef.GROUP] = GroupDomain.INVESTMENT
    base_descr = str(assets_file_row.get(AssetsDef.DESCR) or asset_id).strip() or asset_id
    row[AssetsDef.DESCR] = f"{base_descr} (0 poz.)"

    result = pd.DataFrame([row])
    AssetsDef.check_structure(result)
    return format_date_columns(result, AssetsDef.EVALUATION_DATE), warnings
