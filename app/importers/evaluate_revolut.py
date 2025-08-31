# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from importers.read_r_transactions import read_revolut_transactions
from importers.rec_as_asset import rec_as_asset


def evaluate_revolut(data_root: Path = None, asset_id: str = None):
    p = data_root / asset_id
    if not p.is_dir():
        raise ValueError(p)
    df = read_revolut_transactions(p, asset_id)
    last =df[-1:]
    for i, row in last.iterrows():
        iban = ''  #
        data = row['Data zrealizowania']
        value = row['Saldo']
        d = rec_as_asset(asset_id, data, value, iban)
        break
    data = [d]
    df_m_23 = pd.DataFrame(data=data)
    return df_m_23
