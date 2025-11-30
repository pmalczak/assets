# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from analyse_assets.select_asset import select_asset


def opoczynska(df: pd.DataFrame, fout: Path, result: dict) -> pd.DataFrame:
    m1 = (
        (df["#Tytuł"] == "UMOWA KREDYTOWA E0891681 KREDYTOBIORCA MARCIN TYNECKI")
        | (df["#Tytuł"] == "KUPNO MIESZKANIA OPOCZYŃSKA 14/14")
    )

    selector = m1
    return select_asset(df, selector, fout, result)
