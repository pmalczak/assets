# -*- coding: utf-8 -*-
__author__ = 'pmalczak@gmail.com'
from pathlib import Path
import pandas as pd

from data_step.data_step import DATA_STEP

revolut_file_structure = [
    'Rodzaj', 'Produkt', 'Data rozpoczęcia', 'Data zrealizowania', 'Opis', 'Kwota', 'Opłata', 'Waluta', 'State', 'Saldo'
]


def read_revolut_transactions(input_path: Path, asset_id: str) -> pd.DataFrame:
    resource = f'{asset_id}.parquet'
    r = DATA_STEP.obtain(resource, _read_revolut_transactions, input_path=input_path)
    result = r.data_frame()
    return result


def _read_revolut_transactions(input_path: Path = None) -> pd.DataFrame:
    input_files = list(input_path.glob('*.csv'))
    if not input_files:
        df = pd.DataFrame(data=None, columns=revolut_file_structure)
        return df

    result = []
    for input_file in input_files:
        r_transactions = pd.read_csv(input_file)

        print(f'PLIK:{input_file} {len(r_transactions):>4} rekord/ów')
        result += [r_transactions]

    result = pd.concat(result)
    return result
