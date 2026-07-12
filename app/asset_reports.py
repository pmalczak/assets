# -*- coding: utf-8 -*-
"""Raporty tekstowe uzywane przez main.py i app_assets.py."""

from __future__ import annotations

import pandas as pd

from importers.assets.data_model import AssetsDef

_SEPARATOR = "________________________________________________\n"
_COL_SPACE = 15


def rap2(assets: pd.DataFrame) -> None:
    print("RAP 2___________________________________________")
    a1 = assets[[AssetsDef.TYPE, AssetsDef.VALUE, AssetsDef.VALUE_PLN, AssetsDef.CURRENCY]]

    a1_sum = a1.copy()
    a1_sum[AssetsDef.TYPE] = "Z RAZEM"
    a1 = pd.concat([a1, a1_sum])

    g1 = a1.groupby([AssetsDef.TYPE, AssetsDef.CURRENCY]).sum().round().astype(int)
    g1 = g1.unstack(AssetsDef.CURRENCY)
    g1.columns = [f"{col}_{cur}".lower() for col, cur in g1.columns]

    for col in g1.columns:
        g1[col] = g1[col].map("{:,}".format).str.replace(",", " ")

    print(g1.to_string(col_space=_COL_SPACE))
    print(_SEPARATOR)


def rap1(assets: pd.DataFrame) -> pd.DataFrame:
    a1 = assets[[AssetsDef.GROUP, AssetsDef.CURRENCY, AssetsDef.VALUE_PLN]]
    a2 = a1.copy()
    a2[AssetsDef.GROUP] = "Z RAZEM"
    a3 = a1.copy()
    a3[AssetsDef.CURRENCY] = "RAZEM"
    a4 = a3.copy()
    a4[AssetsDef.GROUP] = "Z RAZEM"

    df = pd.concat([a1, a2, a3, a4])
    g1 = df.groupby([AssetsDef.GROUP, AssetsDef.CURRENCY]).sum()
    g1 = g1.unstack(AssetsDef.CURRENCY).fillna(0)
    g1.columns = g1.columns.get_level_values(1)

    for col in g1.columns:
        g1[col] = g1[col].round().astype(int).map("{:,}".format).str.replace(",", " ")

    return g1
