# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from analyse_assets.data_model import AssetRw
from analyse_assets.select_asset import print_asset, select_asset


def aquamarina(df: pd.DataFrame, fout: Path, result: dict) -> pd.DataFrame:
    m = (
        df[AssetRw.MBANK_TITLE].str.contains("UMOWA NR AQ/2014/252/180 LOKAL 180")
    )
    df, r0 = select_asset(df, m, AssetRw.initial_investment_mapping)

    m = (
            df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("AQUAMARINA") |
            df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("MIĘDZYZDROJE") |
            df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("MARINA INVEST") |
            df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("KORNELIA ZAJĄCZKOWSKA")  #
    )
    df, r1 = select_asset(df, m, AssetRw.inflow_outflow_mapping)

    m = df[AssetRw.MBANK_ACCOUNT_NUMBER].str.contains("10124069600163204573190024")
    df, r2 = select_asset(df, m, AssetRw.inflow_outflow_mapping)
    m = (
        df[AssetRw.MBANK_TITLE].str.contains("ZALICZKA DO ZLECENIA 20020793 ZA NAROŻNIK I MATERAC")
    )
    df, r3 = select_asset(df, m, AssetRw.inflow_outflow_mapping)

    r = pd.concat([r0, r1, r2, r3])
    print_asset(r, fout, result)
    return df
