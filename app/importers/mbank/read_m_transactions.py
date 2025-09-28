# -*- coding: utf-8 -*-
__author__ = 'pmalczak@gmail.com'
from pathlib import Path
import pandas as pd

from data_step.data_step import DATA_STEP
from importers.mbank.data_model import MBankFile
from importers.mbank.local_extract_csv_table import ForbiddenSign, NoData
from importers.mbank.local_read_csv_file import read_mbank_csv_file


def read_m_transactions(input_path: Path, asset_id: str) -> pd.DataFrame:
    resource = f'01 source/{asset_id}.parquet'
    r = DATA_STEP.obtain(resource, _read_m_transactions, input_path=input_path)
    result = r.data_frame()
    return result


def _read_m_transactions(input_path: Path = None) -> pd.DataFrame:
    input_files = list(input_path.glob('*.csv'))
    if not input_files:
        df = pd.DataFrame(data=None, columns=list(MBankFile.expected_columns()))
        return df

    forbidden_signs = []
    result = []
    for input_file in input_files:
        try:
            mbank_transactions = read_mbank_csv_file(input_file)
        except ForbiddenSign as e:
            m = f'plik:{input_file} \nznak \" w {e.args[0]}'
            print(m)
            forbidden_signs += [m]
            continue

        except NoData:
            print(f'PLIK:{input_file}      brak danych ')
            continue

        print(f'PLIK:{input_file} {len(mbank_transactions):>4} rekord/ów')
        result += [mbank_transactions]

    if forbidden_signs:
        raise ForbiddenSign(forbidden_signs)

    result = pd.concat(result)
    return result
