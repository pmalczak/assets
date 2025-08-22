# -*- coding: utf-8 -*-
__author__ = 'pmalczak@gmail.com'

from pathlib import Path

import pandas as pd

from .read_m_transactions import read_m_transactions


def read_m_test_transactions(p: Path) -> pd.DataFrame:
    lst = list(filter(lambda x: x.is_dir(), p.glob('*')))
    result = []
    for mbank_transactions_path in lst:
        r = read_m_transactions(mbank_transactions_path)
        if not r.empty:
            result += [r]
    result = pd.concat(result)
    return result
