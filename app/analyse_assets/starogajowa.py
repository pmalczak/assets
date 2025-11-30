# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from analyse_assets.select_asset import select_asset


def starogajowa(df: pd.DataFrame, fout: Path, result: dict) -> pd.DataFrame:
    m1 = (
            df["#Tytuł"].str.contains("STAROGAJOWA")
            # df["#Nadawca/Odbiorca"].str.contains("MIĘDZYZDROJE") |
            # df["#Nadawca/Odbiorca"].str.contains("MARINA INVEST") #
    )
    m2 = (
        df["#Tytuł"].str.contains("DEPOZYT DO UMOWY SPRZEDAŻY STAROGAJOWA 23")
        | df["#Tytuł"].str.contains("ZADATEK-UMOWA PRZEDWSTĘPNA-SPRZEDAŻ STAROGAJOWA 23")
        | df["#Tytuł"].str.contains("OPŁATA NOTARIALNA + PODATEK ZA SPRZEDAŻ STAROGAJOWA 23")
    )

    selector = m1 | m2
    return select_asset(df, selector, fout, result)
