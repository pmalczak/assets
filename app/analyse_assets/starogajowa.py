# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from analyse_assets.select_asset import select_asset


def starogajowa(df: pd.DataFrame, fout: Path, result: dict) -> pd.DataFrame:
    m1 = (
        df["#Tytuł"].str.contains("STAROGAJOWA")
        | df["#Tytuł"].str.contains("DEPOZYT DO UMOWY SPRZEDAŻY STAROGAJOWA 23")
        | df["#Tytuł"].str.contains("ZADATEK-UMOWA PRZEDWSTĘPNA-SPRZEDAŻ STAROGAJOWA 23")
        | df["#Tytuł"].str.contains("OPŁATA NOTARIALNA + PODATEK ZA SPRZEDAŻ STAROGAJOWA 23")
        | df["#Tytuł"].str.contains("FV73/2019")
    )

    selector = m1
    return select_asset(df, selector, fout, result)
