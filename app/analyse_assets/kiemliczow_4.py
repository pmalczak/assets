# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from analyse_assets.data_model import AssetRw
from analyse_assets.select_asset import select_asset, print_asset


def kiemliczow_4(df: pd.DataFrame, fout: Path, result: dict) -> pd.DataFrame:
    m = (
        df[AssetRw.MBANK_TITLE].str.contains("KIEMLICZÓW 9/4")
        | df[AssetRw.MBANK_TITLE].str.contains("CZYNSZ + POMIESZCZENIE GOSPODARCZE (51,00)", regex=False)
        | (df[AssetRw.MBANK_TITLE] == "TAURON KIEMLICZÓW 4 ")
    ) #
    df, r1 = select_asset(df, m, AssetRw.inflow_outflow_mapping)
    m = (
            df[AssetRw.MBANK_ACCOUNT_NUMBER] == "5110205242676676767"
    )
    df, r2 = select_asset(df, m, AssetRw.inflow_outflow_mapping)

    r = pd.concat([r1, r2])
    print_asset(r, fout, result)
    return df
