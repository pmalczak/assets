# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

import pandas as pd

from mbank_logs.data_model import MBANK_TRANSACTION_DATE, MBANK_OUTSTANDING_BALANCE, MBANK_DEBIT_ACCOUNT
from mbank_logs.read_m_transactions import read_m_transactions


def mbank_evaluate(my_data_path, asset_id):
    p = my_data_path / asset_id
    if not p.is_dir():
        raise ValueError(p)
    df = read_m_transactions(p)
    last =df[-1:]
    for i, row in last.iterrows():
        d = {
            'id': asset_id,
            'data wyceny': row[MBANK_TRANSACTION_DATE],
            'wartość': row[MBANK_OUTSTANDING_BALANCE],
            'IBAN': row[MBANK_DEBIT_ACCOUNT]
        }
        break
    df_m_23 = pd.DataFrame(data=[d])
    return df_m_23
