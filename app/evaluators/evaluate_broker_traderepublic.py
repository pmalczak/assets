# -*- coding: utf-8 -*-
"""Snapshot BROKER Trade Republic: depozyt cash-only — NAV = Σ(amount−|fee|−|tax|)."""
from __future__ import annotations

__author__ = "pmalczak@gmail.com"

from datetime import date
from pathlib import Path

import pandas as pd

from app_proc.data_root import resolve_asset_dir
from evaluators.broker_snapshot import (
    BrokerHoldings,
    BrokerSnapshotEvaluator,
    empty_broker_snapshot,
    snapshot_from_holdings,
)
from evaluators.valuation_date import filter_on_or_before
from importers.assets.data_model import AssetsDef, GroupDomain, TypeDomain
from importers.traderepublic.data_model import DEFAULT_TRADEREPUBLIC_ASSET_ID, TradeRepublicFile
from importers.traderepublic.read_traderepublic import read_traderepublic_transactions
from roi.statement_valuation_date import evaluation_date_from_frame
from roi.traderepublic_deposit_roi import nav_as_of


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
        catalog_ccy = str(assets_file_row.get(AssetsDef.CURRENCY) or "").strip() or None
        if not p.is_dir():
            warnings.append(
                f"Brak katalogu {p} — uruchom Import wyciągów "
                f"(Eksport transakcji.csv → assets/{asset_id}/)."
            )
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

        blotter = read_traderepublic_transactions(p, asset_id)
        if blotter.empty:
            warnings.append("Brak eksportów Trade Republic w katalogu assetu.")
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

        nav, nav_warnings = nav_as_of(blotter, valuation_date)
        warnings.extend(nav_warnings)
        used = filter_on_or_before(blotter, TradeRepublicFile.DATE, valuation_date)
        eval_date = evaluation_date_from_frame(
            used, TradeRepublicFile.FILE_DATE, valuation_date
        ) or valuation_date.isoformat()
        # Depozyt = ekspozycja XIRR: NAV w positions_value, cash_value=0
        # (żeby strip broker-cash nie zerował terminala portfela).
        n_cash = int(len(used)) if not used.empty else 0
        return (
            BrokerHoldings(
                positions_value=float(nav),
                cash_value=0.0,
                n_positions=0,
                n_cash_rows=n_cash,
                evaluation_date=eval_date,
                currency=catalog_ccy,
            ),
            warnings,
        )

    def evaluate(
        self,
        data_root: Path,
        asset_id: str,
        assets_file_row: pd.Series,
        valuation_date: date,
    ) -> tuple[pd.DataFrame, list[str]]:
        holdings, warnings = self.load_holdings(
            data_root, asset_id, assets_file_row, valuation_date
        )
        if holdings is None:
            return empty_broker_snapshot(), warnings
        result = snapshot_from_holdings(assets_file_row, asset_id, holdings)
        # Snapshot: typ/grupa jak depozyt (katalog może zostać BROKER / udziały).
        result[AssetsDef.TYPE] = TypeDomain.DEPOSIT
        result[AssetsDef.GROUP] = GroupDomain.DEPOSIT
        base = str(assets_file_row.get(AssetsDef.DESCR) or asset_id).strip() or asset_id
        result[AssetsDef.DESCR] = f"{base} (depozyt TR)"
        return result, warnings


def evaluate_broker_traderepublic(
    data_root: Path,
    asset_id: str,
    assets_file_row: pd.Series,
    valuation_date: date,
) -> tuple[pd.DataFrame, list[str]]:
    """Wycena rachunku Trade Republic jako oprocentowanego depozytu (cash-only v1)."""
    return TradeRepublicSnapshotEvaluator().evaluate(
        data_root, asset_id, assets_file_row, valuation_date
    )
