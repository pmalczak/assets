# -*- coding: utf-8 -*-
from __future__ import annotations

__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from analyse_assets.consolidate_and_drop_internal_transfers import consolidate_many_drop_internal_transfers
from analyse_assets.data_model import AssetRw
from analyse_assets.select_asset import print_asset
from data_step.data_step import DATA_STEP
from importers.assets.data_model import AssetsFile, KindDomain
from importers.assets.read_assets import read_assets
from importers.mbank.read_m_transactions import read_m_transactions
from app_proc.data_root import get_online_data_root
from roi.allocate import allocate_catalog
from roi.config import read_analyse_config


def main():

    DATA_STEP.init_steps(root=Path(__file__))
    # DATA_STEP.force_read_data()
    assets = read_assets()
    assets = assets[assets[AssetsFile.KIND].str.startswith(KindDomain.MBANK)]
    assets = assets[assets[AssetsFile.CURRENCY] == "PLN"]
    assets = assets[AssetsFile.ID].tolist()

    data_root = get_online_data_root()
    result = []
    for asset in assets:
        df = read_m_transactions(data_root, asset)
        df["_source"] = asset
        result.append(df)

    df, report, meta = consolidate_many_drop_internal_transfers(result)
    df = AssetRw.add_ymd_columns(df)

    p = Path(__file__).parent
    df = analyse_assets_proc(df, p)
    print(meta)

    file_out = p / "mbank_consolidated.xlsx"
    df.to_excel(file_out, index=False)

    # file_out = p / "mbank_consolidated.parquet"
    # df.to_parquet(file_out, compression=None)
    return


def analyse_assets_proc(
    df: pd.DataFrame,
    output_dir: Path,
    config_path: Path | None = None,
) -> pd.DataFrame:
    config = read_analyse_config(config_path)
    catalog = (
        config["catalog"]
        .sort_values("order")
        .reset_index(drop=True)
    )
    catalog = catalog[catalog["enabled"].astype(bool)]

    events_by_asset = allocate_catalog(df, catalog, config["rules"], config["manual"])

    result: dict[Path, pd.DataFrame] = {}
    for _, asset_row in catalog.iterrows():
        asset_id = str(asset_row["asset_id"])
        file_out = output_dir / str(asset_row["output_file"])
        selected = events_by_asset.get(asset_id, pd.DataFrame())
        if selected.empty:
            continue
        raw = _events_to_asset_rw(selected)
        result[file_out] = raw
        print_asset(raw, file_out, result)

    for file_path, asset_df in result.items():
        asset_df.to_excel(file_path, index=False)

    return df


def _events_to_asset_rw(events: pd.DataFrame) -> pd.DataFrame:
    from roi.categories import ROI_TO_ASSET_RW

    rows = []
    for _, row in events.iterrows():
        rows.append(
            (
                row["date"],
                row["amount"],
                ROI_TO_ASSET_RW[row["category"]],
                row["description"],
            )
        )
    return AssetRw.create(rows)


if __name__ == "__main__":
    pd.options.future.infer_string = True

    pd.set_option("display.max_rows", None)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 5000)
    pd.set_option("display.colheader_justify", "center")
    main()
