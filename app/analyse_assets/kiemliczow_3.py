# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from analyse_assets.data_model import AssetRw
from analyse_assets.select_asset import select_asset, print_asset


def kiemliczow_3(df: pd.DataFrame, fout: Path, result: dict) -> pd.DataFrame:
    m = (
            df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("GRZEGORZ KOPACKI") |
            df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("GRZEGORZ I AGATA KOPACCY")
    )
    df, r1 = select_asset(df, m, AssetRw.initial_investment_mapping)
    m = (
        df[AssetRw.MBANK_TITLE].str.contains("KIEMLICZÓW 9/3")
    )
    df, r2 = select_asset(df, m, AssetRw.inflow_outflow_mapping)

    r = pd.concat([r1, r2])
    print_asset(r, fout, result)
    return df
