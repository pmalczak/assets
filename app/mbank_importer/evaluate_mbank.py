# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from data_step.data_step import DATA_STEP
from mbank_logs.data_model import MBANK_TRANSACTION_DATE, MBANK_OUTSTANDING_BALANCE, MBANK_DEBIT_ACCOUNT, MBANK_AMOUNT
from mbank_logs.read_m_transactions import read_m_transactions


def evaluate_mbank(data_root, asset_id: str) -> pd.DataFrame:
    assert isinstance(asset_id, str)
    r = DATA_STEP.obtain(f'mbank/{asset_id}_evaluation.parquet', _evaluate_mbank,
                         data_root=data_root, asset_id=asset_id)
    return r.data_frame()


def _evaluate_mbank(data_root: Path = None, asset_id: str = None):
    p = data_root / asset_id
    if not p.is_dir():
        raise ValueError(p)
    df = read_m_transactions(p, asset_id)
    last =df[-1:]
    for i, row in last.iterrows():
        iban = row[MBANK_DEBIT_ACCOUNT]
        value = row[MBANK_OUTSTANDING_BALANCE]
        d = rec_as_asset(row, asset_id, value, iban)
        break
    data = [d]
    df_m_23 = pd.DataFrame(data=data)
    return df_m_23


def rec_as_asset(row, asset_id, value, iban):
    d = {
        'id': asset_id,
        'data wyceny': row[MBANK_TRANSACTION_DATE],
        'wartość': value,
        'IBAN': iban
    }
    return d
