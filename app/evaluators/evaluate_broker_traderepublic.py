# -*- coding: utf-8 -*-
"""Snapshot BROKER Trade Republic: 1 wiersz; na start NAV=0 (brak pozycji instrumentów)."""
from __future__ import annotations

__author__ = "pmalczak@gmail.com"

from datetime import date
from pathlib import Path

import pandas as pd

from app_proc.data_root import resolve_asset_dir
from evaluators.broker_snapshot import BrokerHoldings, BrokerSnapshotEvaluator
from importers.assets.data_model import AssetsDef
from importers.traderepublic.data_model import DEFAULT_TRADEREPUBLIC_ASSET_ID
from importers.traderepublic.read_traderepublic import read_traderepublic_transactions


def is_traderepublic_broker(assets_file_row: pd.Series) -> bool:
    asset_id = str(assets_file_row.get(AssetsDef.ID, "")).strip()
    return asset_id == DEFAULT_TRADEREPUBLIC_ASSET_ID


class TradeRepublicSnapshotEvaluator(BrokerSnapshotEvaluator):
    def matches(self, assets_file_row: pd.Series) -> bool:
        return is_traderepublic_broker(assets_file_row)

    def load_holdings(
        self,
        data_root: Path,
        asset_id: str,
        assets_file_row: pd.Series,
        valuation_date: date,
    ) -> tuple[BrokerHoldings | None, list[str]]:
        p = resolve_asset_dir(asset_id, assets_file_row[AssetsDef.TYPE])
        warnings: list[str] = []
        if not p.is_dir():
            warnings.append(
                f"Brak katalogu {p} — uruchom Import wyciągów "
                f"(Eksport transakcji.csv → assets/{asset_id}/)."
            )
        else:
            blotter = read_traderepublic_transactions(p, asset_id)
            if blotter.empty:
                warnings.append("Brak eksportów Trade Republic w katalogu assetu.")
            else:
                warnings.append(
                    "Trade Republic: wycena pozycji instrumentów jeszcze niezaimplementowana "
                    "(NAV kontenera = 0; top-up poza FIFO)."
                )
        catalog_ccy = str(assets_file_row.get(AssetsDef.CURRENCY) or "").strip() or None
        return (
            BrokerHoldings(
                positions_value=0.0,
                cash_value=0.0,
                n_positions=0,
                n_cash_rows=0,
                evaluation_date=valuation_date.isoformat(),
                currency=catalog_ccy,
            ),
            warnings,
        )


def evaluate_broker_traderepublic(
    data_root: Path,
    asset_id: str,
    assets_file_row: pd.Series,
    valuation_date: date,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Syntetyczna wycena rachunku Trade Republic.
    Na start: brak mapowania BUY/SELL → NAV=0 (pozycje i gotówka niezaimplementowane).
    """
    return TradeRepublicSnapshotEvaluator().evaluate(
        data_root, asset_id, assets_file_row, valuation_date
    )
