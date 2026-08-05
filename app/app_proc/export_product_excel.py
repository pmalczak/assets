# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from analyse_assets.config_model import AnalyseAssetsCatalog
from app_proc.data_root import get_online_data_output

ASSETS_EVALUATION_FILE = "assets_evaluation.xlsx"


def unallocated_excel_filename(pool_id: str) -> str:
    return f"unallocated_{pool_id}.xlsx"


def roi_summary_excel_filename(snapshot_date: date) -> str:
    return f"roi_{snapshot_date:%Y-%m-%d}.xlsx"


def export_assets_evaluation(df: pd.DataFrame, snapshot_date: date) -> Path:
    target = get_online_data_output(snapshot_date) / ASSETS_EVALUATION_FILE
    df.to_excel(target, index=False)
    return target


def export_roi_summary_excel(summary: pd.DataFrame, snapshot_date: date) -> Path:
    target = get_online_data_output(snapshot_date) / roi_summary_excel_filename(snapshot_date)
    summary.to_excel(target, index=False)
    return target


def export_roi_product_excels(
    events_by_asset: dict[str, pd.DataFrame],
    unallocated_by_pool: dict[str, pd.DataFrame],
    catalog: pd.DataFrame,
    snapshot_date: date,
) -> Path:
    """Zapisuje per-asset Excel + unallocated_{pool_id}.xlsx do product/{date}/."""
    out_dir = get_online_data_output(snapshot_date)

    enabled = catalog[catalog[AnalyseAssetsCatalog.ENABLED].astype(bool)].sort_values(
        AnalyseAssetsCatalog.ORDER
    )
    for _, asset_row in enabled.iterrows():
        asset_id = str(asset_row[AnalyseAssetsCatalog.ASSET_ID])
        if AnalyseAssetsCatalog.OUTPUT_FILE in asset_row.index and pd.notna(
            asset_row[AnalyseAssetsCatalog.OUTPUT_FILE]
        ):
            output_file = str(asset_row[AnalyseAssetsCatalog.OUTPUT_FILE])
        else:
            output_file = f"mbank_{asset_id}.xlsx"
        events = events_by_asset.get(asset_id, pd.DataFrame())
        events.to_excel(out_dir / output_file, index=False)

    for pool_id, unallocated in unallocated_by_pool.items():
        unallocated.to_excel(out_dir / unallocated_excel_filename(pool_id), index=False)

    return out_dir


def list_roi_product_excel_files(snapshot_date: date) -> list[Path]:
    """Pliki Excel ROI w product/{date}: roi_*, unallocated_*, mbank_*."""
    out_dir = get_online_data_output(snapshot_date)
    if not out_dir.is_dir():
        return []
    names = sorted(out_dir.glob("*.xlsx"))
    preferred_prefixes = ("roi_", "unallocated_", "mbank_")
    result = [p for p in names if p.name.startswith(preferred_prefixes)]
    return result
