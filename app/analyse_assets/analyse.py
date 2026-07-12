# -*- coding: utf-8 -*-
from __future__ import annotations

__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from analyse_assets.build_selector import build_step_selector, get_mapping, CATEGORY_MAP
from analyse_assets.config_model import AnalyseAssetsManual, AnalyseAssetsRules
from analyse_assets.data_model import AssetRw
from analyse_assets.read_config import read_analyse_config
from analyse_assets.select_asset import print_asset, select_asset
from analyse_assets.consolidate_and_drop_internal_transfers import consolidate_many_drop_internal_transfers
from data_step.data_step import DATA_STEP
from importers.assets.data_model import AssetsFile, KindDomain
from importers.assets.read_assets import read_assets
from importers.mbank.read_m_transactions import read_m_transactions
from app_proc.data_root import get_online_data_root


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
    df = AssetRw.extract_ymd(df)

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

    result: dict[Path, pd.DataFrame] = {}
    for _, asset_row in catalog.iterrows():
        asset_id = str(asset_row["asset_id"])
        file_out = output_dir / str(asset_row["output_file"])
        df, selected = analyse_single_asset(
            df,
            asset_id,
            config["rules"],
            config["manual"],
        )
        result[file_out] = selected
        print_asset(selected, file_out, result)

    for file_path, asset_df in result.items():
        asset_df.to_excel(file_path, index=False)

    return df


def analyse_single_asset(
    df: pd.DataFrame,
    asset_id: str,
    rules: pd.DataFrame,
    manual: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    asset_rules = rules[rules[AnalyseAssetsRules.ASSET_ID] == asset_id].copy()
    asset_manual = manual[manual[AnalyseAssetsManual.ASSET_ID] == asset_id].copy()

    steps: list[tuple[str, int, object]] = []

    if not asset_rules.empty:
        for (step_id, step_order), step_rules in asset_rules.groupby(
            [AnalyseAssetsRules.STEP_ID, AnalyseAssetsRules.STEP_ORDER],
            sort=False,
        ):
            steps.append(("rule", int(step_order), (str(step_id), step_rules)))

    if not asset_manual.empty:
        for step_order, step_rows in asset_manual.groupby(AnalyseAssetsManual.STEP_ORDER, sort=True):
            steps.append(("manual", int(step_order), step_rows))

    steps.sort(key=lambda item: item[1])

    parts: list[pd.DataFrame] = []
    for step_kind, _, payload in steps:
        if step_kind == "manual":
            parts.append(_build_manual_part(payload))
            continue

        step_id, step_rules = payload
        mapping_name = str(step_rules[AnalyseAssetsRules.MAPPING].iloc[0])
        selector = build_step_selector(df, step_rules)
        df, selected = select_asset(df, selector, get_mapping(mapping_name))
        parts.append(selected)

    if not parts:
        return df, pd.DataFrame(columns=df.columns)

    return df, pd.concat(parts, ignore_index=True)


def _build_manual_part(step_rows: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in step_rows.iterrows():
        category = CATEGORY_MAP[str(row[AnalyseAssetsManual.CATEGORY])]
        rows.append(
            (
                pd.Timestamp(row[AnalyseAssetsManual.DATE]).strftime("%Y-%m-%d"),
                float(row[AnalyseAssetsManual.AMOUNT]),
                category,
                str(row[AnalyseAssetsManual.DESCRIPTION]),
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
