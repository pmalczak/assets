# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"
import pandas as pd
from importers.mbank.data_model import MBankFileCls


class AssetRWCls(MBankFileCls):
    YEAR = 'ROK'
    MONTH = 'MIESIAC'
    DAY = 'DZIEN'
    CAT = 'category'

    CAT_INVESTMENT = '  INWESTYCJA'
    CAT_INFLOW = ' WPŁYWY'
    CAT_OUTFLOW = ' WYDATKI'

    def __init__(self):
        super().__init__()
        self.inflow_outflow_mapping = {
            'PRZELEW WEWNĘTRZNY PRZYCHODZĄCY': self.CAT_INFLOW,
            'PRZELEW ZEWNĘTRZNY PRZYCHODZĄCY': self.CAT_INFLOW,
            'PRZELEW ZEWNĘTRZNY WYCHODZĄCY': self.CAT_OUTFLOW,
            'PRZELEW WEWNĘTRZNY WYCHODZĄCY': self.CAT_OUTFLOW,
            'PRZELEW SORBNET WYCHODZĄCY': self.CAT_OUTFLOW,
        }
        self.initial_investment_mapping = {
            'PRZELEW ZEWNĘTRZNY WYCHODZĄCY': self.CAT_INVESTMENT,
            'PRZELEW WEWNĘTRZNY WYCHODZĄCY': self.CAT_INVESTMENT,
            'PRZELEW SORBNET WYCHODZĄCY': self.CAT_INVESTMENT,
        }
        self.closing_investment_mapping = {
            'PRZELEW WEWNĘTRZNY PRZYCHODZĄCY': ' ZAMKNIĘCIE',
            'PRZELEW ZEWNĘTRZNY PRZYCHODZĄCY': ' ZAMKNIĘCIE',
        }

    def extract_ymd(self, df):
        # df['Data operacji'] = pd.to_datetime(df[self.MBANK_TRANSACTION_DATE], format='%Y-%m-%d')
        x = pd.to_datetime(df[self.MBANK_TRANSACTION_DATE], format='%Y-%m-%d')

        df[self.YEAR] = x.dt.year.astype('str')
        df[self.MONTH] = x.dt.month
        df[self.DAY] = x.dt.day
        return df


AssetRw = AssetRWCls()
