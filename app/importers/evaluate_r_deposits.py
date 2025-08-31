# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from importers.read_r_transactions import read_revolut_transactions
from importers.rec_as_asset import rec_as_asset


def evaluate_r_deposits(data_root: Path, asset_id: str, waluta: str):
    p = data_root / asset_id
    df = read_revolut_transactions(p, asset_id)

    cond = df['Opis'] == 'Depositing savings'
    df = df[cond]

    result = []
    for i, row in df.iterrows():
        value = - row['Kwota']
        data = row['Data zrealizowania']
        d = rec_as_asset(asset_id, data, value, '')
        result += [d]

    if result:
        result = pd.DataFrame(result)
        result['typ'] = 'depozyt'
        result['opis'] = 'lokata'
        result['rodzaj'] = ''
        result['waluta'] = waluta
        result['grupa'] = '0 środki pieniężne'

    return result
