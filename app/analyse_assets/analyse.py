# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"
from pathlib import Path

import pandas as pd

from analyse_assets.analyse_excel import analyse_assets_proc_excel
from analyse_assets.data_model import AssetRw


def main():
    from consolidate_and_drop_internal_transfers import consolidate_many_drop_internal_transfers
    from data_step.data_step import DATA_STEP
    from importers.assets.data_model import AssetsFile, KindDomain
    from importers.assets.read_assets import read_assets
    from importers.mbank.read_m_transactions import read_m_transactions
    from main_proc.data_root import get_online_data_root

    proj_root = Path(__file__).parent.parent
    DATA_STEP.init_steps(root=proj_root)
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


def analyse_assets_proc(df, output_dir: Path, config_path: Path | None = None):
    return analyse_assets_proc_excel(df, output_dir, config_path=config_path)


if __name__ == "__main__":
    pd.options.future.infer_string = True

    pd.set_option("display.max_rows", None)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 5000)
    pd.set_option("display.colheader_justify", "center")
    main()
