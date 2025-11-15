# -*- coding: utf-8 -*-
__author__ = 'pmalczak@gmail.com'
from pathlib import Path
import pandas as pd

from data_step.data_step import DATA_STEP
from importers.deduplicate_records import deduplicate_records
from importers.revolut.data_model import RevolutFile, RevolutFileState


def read_revolut_account_transactions(input_path: Path, asset_id: str) -> pd.DataFrame:
    resource = f'01 source/{asset_id}-account.parquet'
    r = DATA_STEP.obtain_dependent(resource, _read_revolut_account_transactions, input_path)
    result = r.data_frame()
    return result


def read_revolut_deposit_transactions(input_path: Path, asset_id: str) -> pd.DataFrame:
    resource = f'01 source/{asset_id}-deposit.parquet'
    r = DATA_STEP.obtain_dependent(resource, _read_revolut_deposit_transactions, input_path)
    result = r.data_frame()
    return result


def _read_revolut_account_transactions(source_file: Path = None) -> pd.DataFrame:
    input_files = [f for f in source_file.rglob("account-statement_*.csv")]

    if not input_files:
        df = pd.DataFrame(data=None, columns=list(RevolutFile.expected_columns()))
        return df

    records = []
    for input_file in input_files:
        df = pd.read_csv(input_file)

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


def _read_revolut_deposit_transactions(source_file: Path = None) -> pd.DataFrame:
    input_files = [f for f in source_file.rglob("*.csv") if f.name.startswith(('a3665301-', '5eadd4a3-'))]

    if not input_files:
        df = pd.DataFrame(data=None, columns=list(RevolutFile.expected_columns()))
        return df

    records = []
    for input_file in input_files:
        df = pd.read_csv(input_file)

        df[RevolutFile.DATE] = pd.to_datetime(df["Completed Date"], format="%d %b %Y")
        df[RevolutFile.DATE] = df[RevolutFile.DATE].dt.strftime("%Y-%m-%d")

        df[RevolutFile.BALANCE] = (
            df["Balance"]
            .replace({'€': '', ',': ''}, regex=True)
            .astype(float)
        )

        print(f'PLIK:{input_file} {len(df):>4} rekord/ów')
        records += [df]

    result = None
    for record in records:
        if result is None:
            result = record
            continue

        result = deduplicate_records(result, record, RevolutFile.DATE, RevolutFile.unique_key())

    # result = pd.concat(result)
    # result = result[result['Description'] == 'Money carried forward']
    # result[RevolutFile.INIT_DATE] = result[RevolutFile.INIT_DATE].apply(_strip_date)
    # result[RevolutFile.DATE] = result[RevolutFile.DATE].apply(_strip_date)
    # RevolutFile.check_structure(result)
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
