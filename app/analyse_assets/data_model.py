# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

import pandas as pd

from importers.mbank.data_model import MBankFileCls


class AssetRWCls(MBankFileCls):
    YEAR = 'ROK'
    MONTH = 'MIESIAC'
    DAY = 'DZIEN'

    def x(self, df):
        df['Data operacji'] = pd.to_datetime(df[self.MBANK_TRANSACTION_DATE], format='%Y-%m-%d')

        df[self.YEAR] = df['Data operacji'].dt.year.astype('str')
        df[self.MONTH] = df['Data operacji'].dt.month
        df[self.DAY] = df['Data operacji'].dt.day
        return df


AssetRw = AssetRWCls()
