# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

import re
from pathlib import Path

import pandas as pd

from data_step.data_step import DATA_STEP
from importers.deduplicate_records import deduplicate_records
from importers.revolut.revolut_deposit_file import RevolutDepositFile


def read_revolut_deposit_transactions(input_path: Path, asset_id: str) -> pd.DataFrame:
    resource = f'01 source/{asset_id}-deposit.parquet'
    r = DATA_STEP.obtain_dependent(resource, _read_revolut_deposit_transactions, input_path)
    result = r.data_frame()
    return result


def _read_revolut_deposit_transactions(source_file: Path = None) -> pd.DataFrame:
    pattern = re.compile(r'^.{8}-.{4}-.{4}-.{4}-.{12}\.csv$')
    input_files = [
        f for f in source_file.iterdir()
        if f.is_file() and pattern.match(f.name)
    ]

    if not input_files:
        df = pd.DataFrame(data=None, columns=list(RevolutDepositFile.expected_columns()))
        return df

    records = []
    for input_file in input_files:
        df = pd.read_csv(input_file)
        df = RevolutDepositFile.normalize_dtypes(df)

        print(f'PLIK:{input_file} {len(df):>4} rekord/ów')
        records += [df]

    result = None
    for record in records:
        if result is None:
            result = record
            continue

        result = deduplicate_records(result, record, RevolutDepositFile.COMPLETED_DATE, RevolutDepositFile.unique_key())

    result[RevolutDepositFile.FILE_DATE] = ''
    RevolutDepositFile.check_structure(result)
    return result
