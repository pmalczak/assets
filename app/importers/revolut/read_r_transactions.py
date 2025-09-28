# -*- coding: utf-8 -*-
__author__ = 'pmalczak@gmail.com'
from pathlib import Path
import pandas as pd

from data_step.data_step import DATA_STEP
from importers.revolut.data_model import RevolutFile


def read_revolut_transactions(input_path: Path, asset_id: str) -> pd.DataFrame:
    resource = f'{asset_id}.parquet'
    r = DATA_STEP.obtain(resource, _read_revolut_transactions, input_path=input_path)
    result = r.data_frame()
    return result


def _read_revolut_transactions(input_path: Path = None) -> pd.DataFrame:
    input_files = list(input_path.glob('*.csv'))
    if not input_files:
        df = pd.DataFrame(data=None, columns=list(RevolutFile.expected_columns()))
        return df

    result = []
    for input_file in input_files:
        r_transactions = pd.read_csv(input_file)

        print(f'PLIK:{input_file} {len(r_transactions):>4} rekord/ów')
        result += [r_transactions]

    result = pd.concat(result)
    result[RevolutFile.INIT_DATE] = result[RevolutFile.INIT_DATE].apply(_strip_date)
    result[RevolutFile.DATE] = result[RevolutFile.DATE].apply(_strip_date)
    RevolutFile.check_structure(result)
    return result


def _strip_date(x):
    if isinstance(x, float):
        return ''
    r = x.split(' ')
    assert len(r) == 2
    r = r[0]
    t = r.split('-')
    assert len(t) == 3
    return r