# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from analyse_assets.config_model import AnalyseAssetsCatalog
from app_proc.data_root import get_online_data_output

ASSETS_EVALUATION_FILE = "assets_evaluation.xlsx"
MBANK_CONSOLIDATED_FILE = "mbank_consolidated.xlsx"


def export_assets_evaluation(df: pd.DataFrame, snapshot_date: date) -> Path:
    target = get_online_data_output(snapshot_date) / ASSETS_EVALUATION_FILE
    df.to_excel(target, index=False)
    return target


def export_roi_mbank_excels(
    events_by_asset: dict[str, pd.DataFrame],
    unallocated: pd.DataFrame,
    catalog: pd.DataFrame,
    snapshot_date: date,
) -> Path:
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

    unallocated.to_excel(out_dir / MBANK_CONSOLIDATED_FILE, index=False)
    return out_dir
