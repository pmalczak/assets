# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from app_proc.data_root import resolve_asset_dir
from evaluators.valuation_date import format_date_columns
from importers.assets.data_model import AssetsDef, GroupDomain, TypeDomain
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


def evaluate_broker_xtb(
    data_root: Path,
    asset_id: str,
    assets_file_row: pd.Series,
    valuation_date: date,
) -> tuple[pd.DataFrame, list[str]]:
    """Syntetyczna wycena rachunku XTB: jeden wiersz = MTM pozycji + gotówka."""
    p = resolve_asset_dir(asset_id, assets_file_row[AssetsDef.TYPE])
    warnings: list[str] = []
    if not p.is_dir():
        warnings.append(
            f"Brak katalogu {p} — uruchom Import wyciągów "
            f"(ZIP XTB → assets/{asset_id}/xtb_open_closed_cash_...)."
        )
        return pd.DataFrame(columns=list(AssetsDef.expected_columns())), warnings

    latest = latest_open_as_of(read_xtb_open(p, asset_id), valuation_date)
    if latest.empty:
        warnings.append(f"Brak raportu XTB open <= {valuation_date.isoformat()} w {p}.")
        return pd.DataFrame(columns=list(AssetsDef.expected_columns())), warnings

    position_rows = xtb_open_position_rows(latest)
    cash_rows = xtb_cash_rows(latest)
    total_value = xtb_open_positions_value(latest)

    row = AssetsDef.as_assets_row(assets_file_row)
    row[AssetsDef.VALUE] = total_value
    row[AssetsDef.EVALUATION_DATE] = str(latest[XtbOpenPositionsFile.PERIOD_END].max())
    row[AssetsDef.TYPE] = TypeDomain.EQUITIES
    row[AssetsDef.GROUP] = GroupDomain.INVESTMENT
    row[AssetsDef.CURRENCY] = _currency(assets_file_row, latest)
    base_descr = str(assets_file_row.get(AssetsDef.DESCR) or asset_id).strip() or asset_id
    row[AssetsDef.DESCR] = f"{base_descr} ({len(position_rows)} poz. + {len(cash_rows)} cash)"

    result = pd.DataFrame([row])
    AssetsDef.check_structure(result)
    return format_date_columns(result, AssetsDef.EVALUATION_DATE), warnings


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
