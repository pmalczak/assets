# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from importers.rec_as_asset import rec_as_asset
from mbank_logs.data_model import MBANK_TITLE, MBANK_AMOUNT, MBANK_TRANSACTION_DATE
from mbank_logs.read_m_transactions import read_m_transactions

KOL_LOKATA = 'lokata'


def evaluate_mbank_deposits(data_root: Path, asset_id: str, waluta: str):
    p = data_root / asset_id
    df = read_m_transactions(p, asset_id)

    pattern = r"(NR 0\d{14})"
    df[KOL_LOKATA] = df[MBANK_TITLE].str.extract(pattern, expand=False)

    r = df[df[KOL_LOKATA].notnull()]

    active_deposits = r[[KOL_LOKATA, MBANK_AMOUNT]]
    active_deposits = active_deposits.groupby(KOL_LOKATA).sum()
    active_deposits = active_deposits[active_deposits[MBANK_AMOUNT] < 0.0]
    active_deposits = active_deposits.reset_index()
    active_deposits = active_deposits[[KOL_LOKATA]]

    r = r.merge(active_deposits, on=KOL_LOKATA)

    result = []
    for i, row in r.iterrows():
        value = - row[MBANK_AMOUNT]
        date = row[MBANK_TRANSACTION_DATE]
        d = rec_as_asset(asset_id, date, value, '')
        result += [d]

    if result:
        result = pd.DataFrame(result)
        result['typ'] = 'depozyt'
        result['opis'] = 'lokata'
        result['rodzaj'] = ''
        result['waluta'] = waluta
        result['grupa'] = '0 środki pieniężne'

    return result
