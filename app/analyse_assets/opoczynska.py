# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from analyse_assets.data_model import AssetRw
from analyse_assets.select_asset import select_asset, print_asset


def opoczynska(df: pd.DataFrame, fout: Path, result: dict) -> pd.DataFrame:
    m = (
        (df[AssetRw.MBANK_TITLE] == "UMOWA KREDYTOWA E0891681 KREDYTOBIORCA MARCIN TYNECKI")
        | (df[AssetRw.MBANK_TITLE] == "KUPNO MIESZKANIA OPOCZYŃSKA 14/14")
    )
    df, r1 = select_asset(df, m, AssetRw.initial_investment_mapping)
    # m = (
    #     (df[AssetRw.MBANK_TITLE] == "ZAUŁEK ZŁOTNICKI III")
    #     | (df[AssetRw.MBANK_TITLE] == "TAURON OPOCZYŃSKA")
    # )
    # df, r2 = select_asset(df, m, AssetRw.inflow_outflow_mapping)
    m = (
        (df[AssetRw.MBANK_ACCOUNT_NUMBER] == "43105000996029010240832283") # TAURON
    )
    df, r3 = select_asset(df, m, AssetRw.inflow_outflow_mapping)

    r = pd.concat([r1, r3])
    print_asset(r, fout, result)
    return df
