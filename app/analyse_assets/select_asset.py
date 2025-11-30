# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd


def select_asset(df: pd.DataFrame, selector, fout: Path, result: dict) -> pd.DataFrame:
    selected, remaining = _split(df, selector)

    selected.to_excel(fout, index=False)
    selected = selected[['ROK', '#Kwota', '#Opis operacji']]
    total = selected.copy()
    total['#Opis operacji'] = 'TOTAL'
    piv = pd.concat([selected, total])

    total = piv.copy()
    total['ROK'] = 'RAZEM'
    piv = pd.concat([piv, total])

    tabela = piv.pivot_table(
        index='ROK',
        columns='#Opis operacji',
        values='#Kwota',
        aggfunc='sum',
        fill_value=0
    )
    tabela = tabela.round().astype('int').map('{:,}'.format).replace(',', ' ')
    result[fout] = tabela

    print(fout.name)
    print(tabela.to_string(col_space=15))
    print()

    return remaining


def _split(df, selector):
    _selected = df[selector].copy()
    _remains = df[~selector].copy()
    return _selected, _remains
