# -*- coding: utf-8 -*-
__author__ = 'pmalczak@gmail.com'

import pandas as pd

from gnucash.data_model import GNU_FIELD_ACCOUNT_NAME


def remove_transactions(df: pd.DataFrame, acc_template: str) -> pd.DataFrame:
    trn_id = df[df[GNU_FIELD_ACCOUNT_NAME].str.startswith(acc_template)]
    trn_id = trn_id[['trn_id']]
    trn_id['del'] = 1

    result = pd.merge(df, trn_id, on='trn_id', how='left')
    result = result[result['del'].isnull()]
    result.drop(columns=['del'], inplace=True)

    return result
