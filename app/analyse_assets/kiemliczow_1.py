# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from analyse_assets.data_model import AssetRw
from analyse_assets.select_asset import select_asset, print_asset


def kiemliczow_1(df: pd.DataFrame, fout: Path, result: dict) -> pd.DataFrame:
    m = (
        (df[AssetRw.MBANK_ACCOUNT_NUMBER] == "20102052420000250201100809")
        | (df[AssetRw.MBANK_ACCOUNT_NUMBER] == "20102052420000250201100809")
    )

    df, r = select_asset(df, m, AssetRw.inflow_outflow_mapping)

    # r = pd.concat([r1, r2])
    print_asset(r, fout, result)
    return df
