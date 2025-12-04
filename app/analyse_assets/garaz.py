# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"
import pandas as pd

from analyse_assets.data_model import AssetRw
from analyse_assets.select_asset import select_asset


def garaz(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    m = (
         df[AssetRw.MBANK_TITLE].str.contains("OPŁATA ZA ZAKUP GARAŻU - UL. RUMIANKOWA")
    )
    df, r0 = select_asset(df, m, AssetRw.initial_investment_mapping)
    m = (
         (df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("IGLICA GARAŻ")) |
         (df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("PODATEK GARAŻ"))
    )
    df, r1 = select_asset(df, m, AssetRw.inflow_outflow_mapping)
    m = (
        (df[AssetRw.MBANK_TITLE].str.contains("GARAŻ") & (df["ROK"] >= '2020'))
        | (df[AssetRw.MBANK_TITLE] == 'OPŁATA ZA ZAKUP GARAŻU - UL. RUMIANKOWA')
        | (df[AssetRw.MBANK_TITLE].str.contains("GARAŻ ZA"))
    )
    df, r2 = select_asset(df, m, AssetRw.inflow_outflow_mapping)

    r = pd.concat([r0, r1, r2])
    return df, r
