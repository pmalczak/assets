# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"
import pandas as pd

from analyse_assets.data_model import AssetRw
from analyse_assets.select_asset import select_asset


def opoczynska(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    df, r1 = select_asset(df, (
            (df[AssetRw.MBANK_TITLE] == "UMOWA KREDYTOWA E0891681 KREDYTOBIORCA MARCIN TYNECKI")
            | (df[AssetRw.MBANK_TITLE] == "KUPNO MIESZKANIA OPOCZYŃSKA 14/14")
            ),
            AssetRw.initial_investment_mapping)

    df, r2 = select_asset(df, (
            (df[AssetRw.MBANK_TITLE] == "DAROWIZNA")
            & (df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("KRYSTYNA MALCZAK"))
            & (df[AssetRw.YEAR] == "2022")
            & (df[AssetRw.MBANK_AMOUNT] > 0)
            ),
            AssetRw.investment_refund_mapping)

    df, r3 = select_asset(df, (
        (df[AssetRw.MBANK_ACCOUNT_NUMBER] == "43105000996029010240832283")
        | (df[AssetRw.MBANK_ACCOUNT_NUMBER] == "78102010264322425711480066")
        ),
        AssetRw.inflow_outflow_mapping)

    df, r4 = select_asset(df, (
        df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("PODATEK OPOCZYŃSKA")
        | df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("ZAUŁEK ZŁOTNICKI III")
        | df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("MOICO")
        | df[AssetRw.MBANK_TITLE].str.contains("ZWROT ZA RACHUNKI")
        | df[AssetRw.MBANK_TITLE].str.contains("ZWROT ZA R-KI")
        ),
        AssetRw.inflow_outflow_mapping)

    r = pd.concat([r1, r2, r3, r4])
    return df, r
