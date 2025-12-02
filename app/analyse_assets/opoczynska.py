# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from analyse_assets.data_model import AssetRw
from analyse_assets.select_asset import select_asset


def opoczynska(df: pd.DataFrame, fout: Path, result: dict) -> pd.DataFrame:
    m1 = (
        (df[AssetRw.MBANK_TITLE] == "UMOWA KREDYTOWA E0891681 KREDYTOBIORCA MARCIN TYNECKI")
        | (df[AssetRw.MBANK_TITLE] == "KUPNO MIESZKANIA OPOCZYŃSKA 14/14")
        | (df[AssetRw.MBANK_TITLE] == "ZAUŁEK ZŁOTNICKI III")
        | (df[AssetRw.MBANK_TITLE] == "TAURON OPOCZYŃSKA")
    ) #
    m2 = (
        (df[AssetRw.MBANK_ACCOUNT_NUMBER] == "43105000996029010240832283") # TAURON
        # | (df[AssetRw.MBANK_ACCOUNT_NUMBER] == "41102052421283117588515063")  #
    )

    selector = m1 | m2
    return select_asset(df, selector, fout, result)
