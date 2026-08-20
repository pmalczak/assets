# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from app_proc.data_root import resolve_asset_dir
from evaluators.valuation_date import format_date_columns
from importers.assets.data_model import AssetsDef, GroupDomain, TypeDomain
from importers.xtb.data_model import DEFAULT_XTB_ASSET_ID
from importers.xtb.read_xtb import (
    extract_xtb_report_period,
    latest_xtb_report_as_of,
    read_xtb_open_positions,
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
    """Syntetyczna wycena rachunku XTB: jeden wiersz = MTM z Open Positions."""
    del data_root
    p = resolve_asset_dir(asset_id, assets_file_row[AssetsDef.TYPE])
    warnings: list[str] = []

    row = AssetsDef.as_assets_row(assets_file_row)
    row[AssetsDef.TYPE] = TypeDomain.EQUITIES
    row[AssetsDef.GROUP] = GroupDomain.INVESTMENT
    row[AssetsDef.CURRENCY] = str(assets_file_row.get(AssetsDef.CURRENCY) or "PLN").strip() or "PLN"
    row[AssetsDef.EVALUATION_DATE] = valuation_date.isoformat()
    row[AssetsDef.VALUE] = 0.0

    base_descr = str(assets_file_row.get(AssetsDef.DESCR) or asset_id).strip() or asset_id
    if not p.is_dir():
        warnings.append(
            f"Brak katalogu {p} — uruchom Import wyciągów "
            f"(ZIP XTB → assets/{asset_id}/xtb_open_closed_cash_...)."
        )
        row[AssetsDef.DESCR] = f"{base_descr} (0 poz.)"
        return _result(row), warnings

    report = latest_xtb_report_as_of(p, valuation_date, required_kind="open")
    if report is None:
        warnings.append(f"Brak raportu XTB open <= {valuation_date.isoformat()} w {p}.")
        row[AssetsDef.DESCR] = f"{base_descr} (0 poz.)"
        return _result(row), warnings

    open_positions = read_xtb_open_positions(report)
    position_rows = xtb_open_position_rows(open_positions)
    value = xtb_open_positions_value(open_positions)
    _, period_end = extract_xtb_report_period(report)

    row[AssetsDef.VALUE] = value
    row[AssetsDef.EVALUATION_DATE] = period_end.isoformat()
    row[AssetsDef.DESCR] = f"{base_descr} ({len(position_rows)} poz.)"
    return _result(row), warnings


def _result(row: pd.Series) -> pd.DataFrame:
    result = pd.DataFrame([row])
    AssetsDef.check_structure(result)
    return format_date_columns(result, AssetsDef.EVALUATION_DATE)
