# -*- coding: utf-8 -*-
__author__ = 'pmalczak@gmail.com'

from pathlib import Path
import pandas as pd

from data_step.data_step import DATA_STEP
from importers.deduplicate_records import deduplicate_records
from importers.mbank.data_model import MBankFile
from importers.mbank.local_extract_csv_table import ForbiddenSign
from importers.mbank.local_read_csv_file import read_mbank_csv_file


def read_m_transactions(asset_dir: Path, asset_id: str) -> pd.DataFrame:
    """Czyta wyciągi mBank z katalogu aktywa (już rozwiązana ścieżka)."""
    if not asset_dir.is_dir():
        raise ValueError(asset_dir)

    resource = f'01 source/{asset_id}.parquet'
    r = DATA_STEP.obtain_dependent(resource, _read_m_transactions, asset_dir)
    result = r.data_frame()
    return result


def _read_m_transactions(source_file: Path = None) -> pd.DataFrame:

    assert source_file.is_dir()
    input_files = sorted(source_file.glob('*.csv'), key=lambda p: p.name)
    # input_files = list(source_file.glob('*.csv'))
    if not input_files:
        df = pd.DataFrame(data=None, columns=list(MBankFile.expected_columns()))
        MBankFile.check_structure(df)
        return df

    forbidden_signs = []
    records = []
    ref_date = ''
    for input_file in input_files:
        try:
            mbank_transactions, _ref_date = read_mbank_csv_file(input_file)
            ref_date = max(ref_date, _ref_date)
            if len(mbank_transactions) == 0:
                continue

        except ForbiddenSign as e:
            m = f'plik:{input_file} \nznak \" w {e.args[0]}'
            print(m)
            forbidden_signs += [m]
            continue

        print(f'PLIK:{input_file} {len(mbank_transactions):>4} rekord/ów')
        records += [mbank_transactions]

    if forbidden_signs:
        raise ForbiddenSign(forbidden_signs)

    result = None
    for record in records:
        if result is None:
            result = record
            continue

        result = deduplicate_records(result, record, MBankFile.MBANK_TRANSACTION_DATE, MBankFile.unique_key())

    result[MBankFile.FILE_DATE] = ref_date
    MBankFile.check_structure(result)
    return result
