# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from analyse_assets.select_asset import select_asset


def kiemliczow_4(df: pd.DataFrame, fout: Path, result: dict) -> pd.DataFrame:
    m1 = (
        df["#Tytuł"].str.contains("KIEMLICZÓW 9/4")
        | df["#Tytuł"].str.contains("CZYNSZ + POMIESZCZENIE GOSPODARCZE (51,00)")
        | (df["#Tytuł"] == "TAURON KIEMLICZÓW 4 ")
    ) #
    m2 = (
            df["#Numer konta"] == "5110205242676676767"
    )

    selector = m1 | m2
    return select_asset(df, selector, fout, result)
