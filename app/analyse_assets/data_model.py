# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"
import pandas as pd
from importers.mbank.data_model import MBankFileCls


class AssetRWCls(MBankFileCls):
    YEAR = 'ROK'
    MONTH = 'MIESIAC'
    DAY = 'DZIEN'
    CAT = 'category'

    inflow_outflow_mapping = {
        'PRZELEW WEWNĘTRZNY PRZYCHODZĄCY': ' WPŁYWY',
        'PRZELEW ZEWNĘTRZNY PRZYCHODZĄCY': ' WPŁYWY',
        'PRZELEW ZEWNĘTRZNY WYCHODZĄCY': ' WYDATKI',
        'PRZELEW WEWNĘTRZNY WYCHODZĄCY': ' WYDATKI',
        'PRZELEW SORBNET WYCHODZĄCY': ' WYDATKI',
    }
    initial_investment_mapping = {
        'PRZELEW ZEWNĘTRZNY WYCHODZĄCY': '  INWESTYCJA',
        'PRZELEW WEWNĘTRZNY WYCHODZĄCY': '  INWESTYCJA',
        'PRZELEW SORBNET WYCHODZĄCY': '  INWESTYCJA',
    }
    closing_investment_mapping = {
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
