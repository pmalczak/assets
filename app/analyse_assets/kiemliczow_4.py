# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"
import pandas as pd

from analyse_assets.data_model import AssetRw
from analyse_assets.select_asset import select_asset


def kiemliczow_4(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    r0 = AssetRw.create([
        ('2000-02-18', -185000.0, AssetRw.CAT_INVESTMENT, 'zakup mieszkania'),
        ]
    )

    df, r1 = select_asset(df, (
            df[AssetRw.MBANK_TITLE].str.contains("KIEMLICZÓW 9/4")
            | df[AssetRw.MBANK_TITLE].str.contains("CZYNSZ + POMIESZCZENIE GOSPODARCZE (51,00)", regex=False)
            | (df[AssetRw.MBANK_TRANSACTION_PARTY] == "TAURON KIEMLICZÓW 4 ")
            ), AssetRw.inflow_outflow_mapping)

    df, r2 = select_asset(df, (
            (df[AssetRw.MBANK_ACCOUNT_NUMBER] == "78102010264322424265110059")  # TAURON KIEMLICZÓW 4 NOWY
            | (df[AssetRw.MBANK_ACCOUNT_NUMBER] == "47114010100000531029001001")  # ENIGMA
            | (df[AssetRw.MBANK_ACCOUNT_NUMBER] == "31105000996029010224308549")  # TAURON
            ), AssetRw.inflow_outflow_mapping)

    df, r3 = select_asset(df, (
            (df[AssetRw.MBANK_ACCOUNT_NUMBER] == "20102052420000250201100809")
            | (df[AssetRw.MBANK_ACCOUNT_NUMBER] == "20102052420000250201100809")
            | (df[AssetRw.MBANK_TITLE] == "WPŁATA NA FUNDUSZ BUDOWY DROGI PRZY UL. KIEMLICZÓW")  #
            ), AssetRw.inflow_outflow_mapping)

    r = pd.concat([r0, r1, r2, r3])
    # print_asset(r, fout, result)
    return df, r
