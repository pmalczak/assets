# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"
import pandas as pd

from analyse_assets.data_model import AssetRw
from analyse_assets.select_asset import select_asset


def kiemliczow_3(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    m = (
            df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("GRZEGORZ KOPACKI") |
            df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("GRZEGORZ I AGATA KOPACCY")
    )
    df, r1 = select_asset(df, m, AssetRw.initial_investment_mapping)
    m = (
        df[AssetRw.MBANK_TITLE].str.contains("KIEMLICZÓW 9/3")
        | df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("WOJCIECH GOŁĘBIOWSKI  UL.ŚCIEGIENNEGO 69 M.38            30-809 KRAKÓW")
    )
    df, r2 = select_asset(df, m, AssetRw.inflow_outflow_mapping)

    r = pd.concat([r1, r2])
    # print_asset(r, fout, result)
    return df, r
