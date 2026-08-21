# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from app_proc.data_root import resolve_asset_dir
from evaluators.broker_snapshot import BrokerHoldings, BrokerSnapshotEvaluator
from importers.assets.data_model import AssetsDef
from importers.xtb.data_model import DEFAULT_XTB_ASSET_ID, XtbOpenPositionsFile
from importers.xtb.read_xtb import (
    latest_open_as_of,
    read_xtb_open,
    xtb_cash_rows,
    xtb_open_position_rows,
    xtb_open_positions_value,
)


def is_xtb_broker(assets_file_row: pd.Series) -> bool:
    return str(assets_file_row.get(AssetsDef.ID, "")).strip() == DEFAULT_XTB_ASSET_ID


class XtbSnapshotEvaluator(BrokerSnapshotEvaluator):
    def matches(self, assets_file_row: pd.Series) -> bool:
        return is_xtb_broker(assets_file_row)

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
                f"(ZIP XTB → assets/{asset_id}/xtb_open_closed_cash_...)."
            )
            return None, warnings

        latest = latest_open_as_of(read_xtb_open(p, asset_id), valuation_date)
        if latest.empty:
            warnings.append(f"Brak raportu XTB open <= {valuation_date.isoformat()} w {p}.")
            return None, warnings

        position_rows = xtb_open_position_rows(latest)
        cash_rows = xtb_cash_rows(latest)
        return (
            BrokerHoldings(
                positions_value=xtb_open_positions_value(position_rows),
                cash_value=xtb_open_positions_value(cash_rows),
                n_positions=len(position_rows),
                n_cash_rows=len(cash_rows),
                evaluation_date=str(latest[XtbOpenPositionsFile.PERIOD_END].max()),
                currency=_currency(assets_file_row, latest),
            ),
            warnings,
        )


def evaluate_broker_xtb(
    data_root: Path,
    asset_id: str,
    assets_file_row: pd.Series,
    valuation_date: date,
) -> tuple[pd.DataFrame, list[str]]:
    """Syntetyczna wycena rachunku XTB: jeden wiersz = MTM pozycji + gotówka."""
    return XtbSnapshotEvaluator().evaluate(
        data_root, asset_id, assets_file_row, valuation_date
    )


def _currency(assets_file_row: pd.Series, latest: pd.DataFrame) -> str:
    catalog = str(assets_file_row.get(AssetsDef.CURRENCY) or "").strip()
    if catalog:
        return catalog
    if XtbOpenPositionsFile.CURRENCY in latest.columns:
        values = (
            latest[XtbOpenPositionsFile.CURRENCY]
            .dropna()
            .astype(str)
            .str.strip()
        )
        values = values[values.ne("")]
        if len(values):
            return str(values.iloc[-1])
    return "PLN"
