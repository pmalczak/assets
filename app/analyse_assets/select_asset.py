# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"
import pandas as pd

from analyse_assets.data_model import AssetRw


def select_asset(df: pd.DataFrame, selector, mapping: dict) -> tuple:
    selected = df[selector].copy()
    remaining = df[~selector].copy()

    if selected.empty:
        raise ValueError("Selektor nie zwrocil zadnych transakcji")

    cond = selected[AssetRw.MBANK_DESCRIPTION].isin(mapping.keys())
    missing = selected.loc[~cond, AssetRw.MBANK_DESCRIPTION].unique()

    if len(missing) > 0:
        raise ValueError(f"Brakujące wartości w mapowaniu: {missing}")

    selected[AssetRw.CAT] = selected[AssetRw.MBANK_DESCRIPTION].replace(mapping)
    return remaining, selected
