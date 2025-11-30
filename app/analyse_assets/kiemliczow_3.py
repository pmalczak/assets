# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from analyse_assets.select_asset import select_asset


def kiemliczow_3(df: pd.DataFrame, fout: Path, result: dict) -> pd.DataFrame:
    m1 = (
            df["#Nadawca/Odbiorca"].str.contains("GRZEGORZ KOPACKI") |
            df["#Nadawca/Odbiorca"].str.contains("GRZEGORZ I AGATA KOPACCY")
    )
    m2 = (
        df["#Tytuł"].str.contains("DEPOZYT DO UMOWY SPRZEDAŻY STAROGAJOWA 23")
        | df["#Tytuł"].str.contains("KIEMLICZÓW 9/3")
    )

    selector = m1 | m2
    return select_asset(df, selector, fout, result)
