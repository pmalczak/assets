# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from analyse_assets.data_model import AssetRw
from analyse_assets.select_asset import select_asset


def aquamarina(df: pd.DataFrame, fout: Path, result: dict) -> pd.DataFrame:
    m1 = (
            df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("AQUAMARINA") |
            df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("MIĘDZYZDROJE") |
            df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("MARINA INVEST") |
            df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("KORNELIA ZAJĄCZKOWSKA")  #
    )
    m2 = df[AssetRw.MBANK_ACCOUNT_NUMBER].str.contains("10124069600163204573190024")
    m3 = (
        df[AssetRw.MBANK_TITLE].str.contains("ZALICZKA DO ZLECENIA 20020793 ZA NAROŻNIK I MATERAC")
    )

    selector = m1 | m2 | m3
    return select_asset(df, selector, fout, result)


def _garaz(df: pd.DataFrame, fout: Path, result: dict) -> pd.DataFrame:
    m1 = (
         (df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("IGLICA GARAŻ")) |
         (df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("PODATEK GARAŻ"))
    )
    m2 = (
        (df[AssetRw.MBANK_TITLE].str.contains("GARAŻ") & (df["ROK"] >= '2020'))
        | (df[AssetRw.MBANK_TITLE] == 'OPŁATA ZA ZAKUP GARAŻU - UL. RUMIANKOWA')
        | (df[AssetRw.MBANK_TITLE].str.contains("GARAŻ ZA"))
    )

    selector = m1 | m2
    return select_asset(df, selector, fout, result)
