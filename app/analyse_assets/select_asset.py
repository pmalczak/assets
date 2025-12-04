# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"
import pandas as pd

from analyse_assets.data_model import AssetRw


def select_asset(df: pd.DataFrame, selector, mapping: dict) -> tuple:
    selected = df[selector].copy()
    remaining = df[~selector].copy()

    if selected.empty:
        raise ValueError()

    cond = selected[AssetRw.MBANK_DESCRIPTION].isin(mapping.keys())
    missing = selected.loc[~cond, AssetRw.MBANK_DESCRIPTION].unique()

    if len(missing) > 0:
        raise ValueError(f"Brakujące wartości w mapowaniu: {missing}")

    selected[AssetRw.CAT] = selected[AssetRw.MBANK_DESCRIPTION].replace(mapping)
    return remaining, selected


def print_asset(_selected, fout, result: dict):
    selected = _selected[[AssetRw.YEAR, AssetRw.MBANK_AMOUNT, AssetRw.CAT]]
    result[fout] = _selected

    x = _print_asset(selected)

    print(fout.name)
    print(x)
    print()


def _print_asset(selected):
    total = selected.copy()
    total[AssetRw.CAT] = 'TOTAL'
    piv = pd.concat([selected, total])

    total = piv.copy()
    total[AssetRw.YEAR] = 'RAZEM'
    piv = pd.concat([piv, total])

    tabela = piv.pivot_table(
        index=AssetRw.YEAR,
        columns=AssetRw.CAT,
        values=AssetRw.MBANK_AMOUNT,
        aggfunc='sum',
        fill_value=0
    )
    tabela = tabela.round().astype('int').map('{:,}'.format).replace(',', ' ')
    return tabela.to_string(col_space=15)
