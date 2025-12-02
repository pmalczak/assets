# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from analyse_assets.data_model import AssetRw
from analyse_assets.select_asset import select_asset


def kiemliczow_4(df: pd.DataFrame, fout: Path, result: dict) -> pd.DataFrame:
    m1 = (
        df[AssetRw.MBANK_TITLE].str.contains("KIEMLICZÓW 9/4")
        | df[AssetRw.MBANK_TITLE].str.contains("CZYNSZ + POMIESZCZENIE GOSPODARCZE (51,00)")
        | (df[AssetRw.MBANK_TITLE] == "TAURON KIEMLICZÓW 4 ")
    ) #
    m2 = (
            df[AssetRw.MBANK_ACCOUNT_NUMBER] == "5110205242676676767"
    )

    selector = m1 | m2
    return select_asset(df, selector, fout, result)
