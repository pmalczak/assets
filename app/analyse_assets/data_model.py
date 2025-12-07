# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"
import pandas as pd
from importers.mbank.data_model import MBankFileCls, MbankOperationType


class ExpectedPosutiveValue(Exception): pass
class ExpectedNegativeValue(Exception): pass


class AssetRWCls(MBankFileCls):
    YEAR = 'ROK'
    MONTH = 'MIESIAC'
    DAY = 'DZIEN'
    CAT = 'category'

    CAT_INVESTMENT = '  INWESTYCJA'
    CAT_INFLOW = ' WPŁYWY'
    CAT_OUTFLOW = ' WYDATKI'
    CAT_CLOSING = ' ZAMKNIĘCIE'

    def __init__(self):
        super().__init__()
        self.inflow_outflow_mapping = {
            MbankOperationType.PRZELEW_WEWNETRZNY_PRZYCHODZACY: self.CAT_INFLOW,
            MbankOperationType.PRZELEW_ZEWNETRZNY_PRZYCHODZACY: self.CAT_INFLOW,
            MbankOperationType.PRZELEW_ZEWNETRZNY_WYCHODZACY: self.CAT_OUTFLOW,
            MbankOperationType.PRZELEW_WEWNETRZNY_WYCHODZACY: self.CAT_OUTFLOW,
            MbankOperationType.PRZELEW_SORBNET_WYCHODZACY: self.CAT_OUTFLOW,
            MbankOperationType.PRZELEW_EXPRESS_ELIXIR_PRZYCH: self.CAT_OUTFLOW,
            MbankOperationType.PRZELEW_EXPRESSOWY_PRZELEW_PRZYCH: self.CAT_OUTFLOW,
        }
        self.inflow_mapping = {
            MbankOperationType.PRZELEW_WEWNETRZNY_PRZYCHODZACY: self.CAT_INFLOW,
            MbankOperationType.PRZELEW_ZEWNETRZNY_PRZYCHODZACY: self.CAT_INFLOW,
        }
        self.initial_investment_mapping = {
            MbankOperationType.PRZELEW_ZEWNETRZNY_WYCHODZACY: self.CAT_INVESTMENT,
            MbankOperationType.PRZELEW_WEWNETRZNY_WYCHODZACY: self.CAT_INVESTMENT,
            MbankOperationType.PRZELEW_SORBNET_WYCHODZACY: self.CAT_INVESTMENT,
        }
        self.investment_refund_mapping = {
            MbankOperationType.PRZELEW_WEWNETRZNY_PRZYCHODZACY: self.CAT_INVESTMENT,
        }
        self.closing_investment_mapping = {
            MbankOperationType.PRZELEW_WEWNETRZNY_PRZYCHODZACY: self.CAT_CLOSING,
            MbankOperationType.PRZELEW_ZEWNETRZNY_PRZYCHODZACY: self.CAT_CLOSING,
        }

    def extract_ymd(self, df):
        x = pd.to_datetime(df[self.MBANK_TRANSACTION_DATE], format='%Y-%m-%d')

        df[self.YEAR] = x.dt.year.astype('str')
        df[self.MONTH] = x.dt.month
        df[self.DAY] = x.dt.day
        return df

    def check_values(self, _df: pd.DataFrame):
        df = _df.copy()
        for cat, df_group in df.groupby(self.CAT):
            pos = df_group[df_group[self.MBANK_AMOUNT] >= 0.0]
            neg = df_group[df_group[self.MBANK_AMOUNT] < 0.0]
            if cat in (self.CAT_INVESTMENT, self.CAT_OUTFLOW):
                if not pos.empty:
                    raise ExpectedNegativeValue(pos)
            elif cat in (self.CAT_INFLOW, self.CAT_CLOSING):
                if not neg.empty:
                    raise ExpectedPosutiveValue(neg)
            else:
                raise NotImplementedError

    def create(self, data: list) -> pd.DataFrame:
        cols = (
            self.MBANK_TRANSACTION_DATE,
            self.MBANK_AMOUNT,
            self.CAT,
            self.MBANK_DESCRIPTION,
        )
        r0 = pd.DataFrame(data=data, columns=cols)
        r0 = AssetRw.extract_ymd(r0)
        self.check_values(r0)
        return r0


AssetRw = AssetRWCls()
