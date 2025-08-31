# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from importers.rec_as_asset import rec_as_asset


def evaluate_regnology(data_root: Path = None, asset_id: str = None):
    p = data_root / asset_id
    if not p.is_dir():
        raise ValueError(p)
    df = read_regnolgy_transactions(p, asset_id)
    last =df[-1:]
    for i, row in last.iterrows():
        iban = ''  #row[MBANK_DEBIT_ACCOUNT]
        value = row['wartość']
        data = row['Data']
        d = rec_as_asset(asset_id, data, value, iban)
        break
    data = [d]
    df_m_23 = pd.DataFrame(data=data)
    return df_m_23


regnology_file_structure = [
    'Data', 'Opis', 'wartość', 'waluta',
]

def read_regnolgy_transactions(input_path: Path, asset_id: str) -> pd.DataFrame:
    f = input_path / 'rocky-iv.csv'
    result = pd.read_csv(f)
    return result
