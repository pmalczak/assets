# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"
import pandas as pd

from analyse_assets.data_model import AssetRw
from analyse_assets.select_asset import select_asset


def kiemliczow_4(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    r0 = {AssetRw.MBANK_TRANSACTION_DATE: '2000-02-18',
          AssetRw.MBANK_AMOUNT: 185000.0,
          AssetRw.YEAR: '2000',
          AssetRw.MONTH: 2,
          AssetRw.DAY: 18,
          AssetRw.CAT: AssetRw.CAT_INVESTMENT,
          }
    r0 = pd.Series(r0)
    r0 = pd.DataFrame([r0])

    m = (
        df[AssetRw.MBANK_TITLE].str.contains("KIEMLICZÓW 9/4")
        | df[AssetRw.MBANK_TITLE].str.contains("CZYNSZ + POMIESZCZENIE GOSPODARCZE (51,00)", regex=False)
        | (df[AssetRw.MBANK_TRANSACTION_PARTY] == "TAURON KIEMLICZÓW 4 ")
    ) #
    df, r1 = select_asset(df, m, AssetRw.inflow_outflow_mapping)
    m = (
        (df[AssetRw.MBANK_ACCOUNT_NUMBER] == "5110205242676676767")
        | (df[AssetRw.MBANK_ACCOUNT_NUMBER] == "47114010100000531029001001")  # ENIGMA
        | (df[AssetRw.MBANK_ACCOUNT_NUMBER] == "31105000996029010224308549")  # TAURON
    )#

    df, r2 = select_asset(df, m, AssetRw.inflow_outflow_mapping)

    r = pd.concat([r0, r1, r2])
    # print_asset(r, fout, result)
    return df, r
