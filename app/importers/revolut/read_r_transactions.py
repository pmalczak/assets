# -*- coding: utf-8 -*-
__author__ = 'pmalczak@gmail.com'
from pathlib import Path
import pandas as pd

from data_step.data_step import DATA_STEP
from importers.deduplicate_records import deduplicate_records
from importers.revolut.data_model import RevolutFile, RevolutFileState
from importers.revolut.read_revolut_transaction_file import read_revolut_transaction_file


def read_revolut_transactions(input_path: Path, asset_id: str) -> pd.DataFrame:
    resource = f'01 source/{asset_id}.parquet'
    r = DATA_STEP.obtain_dependent(resource, _read_revolut_transactions, input_path)
    result = r.data_frame()
    return result


def _read_revolut_transactions(source_file: Path = None) -> pd.DataFrame:
    # input_files = list(source_file.glob('account-statement_*.{xlsx,csv}'))
    input_files = [f for f in source_file.rglob("*") if f.suffix in [".xlsx", ".csv"]]

    if not input_files:
        df = pd.DataFrame(data=None, columns=list(RevolutFile.expected_columns()))
        return df

    records = []
    for input_file in input_files:
        if input_file.suffix == '.xlsx':
            df = read_revolut_transaction_file(input_file)
        elif input_file.suffix == '.csv':
            df = pd.read_csv(input_file)
        else:
            raise ValueError(input_file)

        print(f'PLIK:{input_file} {len(df):>4} rekord/ów')
        records += [df]

    result = None
    for record in records:
        if result is None:
            result = record
            continue

        result = deduplicate_records(result, record, RevolutFile.DATE, RevolutFile.unique_key())

    # result = pd.concat(result)
    result = result[result[RevolutFile.STATE] == RevolutFileState.CLOSED]
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