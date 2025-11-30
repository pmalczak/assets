# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd


def select_asset(df: pd.DataFrame, selector, fout: Path, result: dict) -> pd.DataFrame:
    df_aquamarina, df = _split(df, selector)

    df_aquamarina.to_excel(fout, index=False)
    df_aquamarina = df_aquamarina[['ROK', '#Kwota', '#Opis operacji']]
    total = df_aquamarina.copy()
    total['#Opis operacji'] = 'TOTAL'
    piv = pd.concat([df_aquamarina, total])
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

    return df


def _split(df, selector):
    _selected = df[selector].copy()
    _remains = df[~selector].copy()
    return _selected, _remains
