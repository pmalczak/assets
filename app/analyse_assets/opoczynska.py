# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from analyse_assets.select_asset import select_asset


def opoczynska(df: pd.DataFrame, fout: Path, result: dict) -> pd.DataFrame:
    m1 = (
        (df["#Tytuł"] == "UMOWA KREDYTOWA E0891681 KREDYTOBIORCA MARCIN TYNECKI")
        | (df["#Tytuł"] == "KUPNO MIESZKANIA OPOCZYŃSKA 14/14")
        | (df["#Tytuł"] == "ZAUŁEK ZŁOTNICKI III")
        | (df["#Tytuł"] == "TAURON OPOCZYŃSKA")
    ) #
    m2 = (
        (df["#Numer konta"] == "43105000996029010240832283") # TAURON
        # | (df["#Numer konta"] == "41102052421283117588515063")  #
    )

    selector = m1 | m2
    return select_asset(df, selector, fout, result)
