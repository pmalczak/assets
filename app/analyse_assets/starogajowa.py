# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"
import pandas as pd

from analyse_assets.data_model import AssetRw
from analyse_assets.select_asset import select_asset


def starogajowa(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    df, r1 = select_asset(df, (
            df[AssetRw.MBANK_TITLE].str.contains("ZADATEK-UMOWA PRZEDWSTĘPNA-SPRZEDAŻ STAROGAJOWA 23")
            | df[AssetRw.MBANK_TITLE].str.contains("DEPOZYT DO UMOWY SPRZEDAŻY STAROGAJOWA 23")
            | df[AssetRw.MBANK_TITLE].str.contains("FV73/2019")
            | df[AssetRw.MBANK_TITLE].str.contains("OPŁATA NOTARIALNA + PODATEK ZA SPRZEDAŻ STAROGAJOWA 23")
            ), AssetRw.initial_investment_mapping)

    df, r2 = select_asset(df, (
            df[AssetRw.MBANK_TITLE].str.contains("STAROGAJOWA")
            | (df[AssetRw.MBANK_ACCOUNT_NUMBER] == "06102010269321202107100005")  # PGNIG STAROGAJOWA
            ), AssetRw.inflow_outflow_mapping)

    df, r3 = select_asset(df, (
            df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("PGNIG STAROGAJOWA INDYWIDUALNE KONTO")
            | df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("TAURON STAROGAJOWA")
            | df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("MPWIK STAROGAJOWA")
            ), AssetRw.inflow_outflow_mapping)

    r = pd.concat([r1, r2, r3])
    return df, r
