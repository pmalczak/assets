# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"
import pandas as pd

from analyse_assets.account_tx import AccountTx, add_ymd_columns
from importers.mbank.data_model import MbankOperationType
from importers.revolut.account_data_model import RevolutOperationType


class ExpectedPositiveValue(Exception):
    pass


class ExpectedNegativeValue(Exception):
    pass


class AssetRWCls:
    """Warstwa ROI na kolumnach AccountTx."""

    YEAR = AccountTx.YEAR
    MONTH = AccountTx.MONTH
    DAY = AccountTx.DAY
    CAT = AccountTx.CAT

    TRANSACTION_DATE = AccountTx.TRANSACTION_DATE
    OPERATION_TYPE = AccountTx.OPERATION_TYPE
    TITLE = AccountTx.TITLE
    COUNTERPARTY = AccountTx.COUNTERPARTY
    ACCOUNT_NUMBER = AccountTx.ACCOUNT_NUMBER
    AMOUNT = AccountTx.AMOUNT
    BALANCE = AccountTx.BALANCE
    ACCOUNT_ID = AccountTx.ACCOUNT_ID
    POOL_ID = AccountTx.POOL_ID

    CAT_INVESTMENT = "  INWESTYCJA"
    CAT_INFLOW = " WPŁYWY"
    CAT_OUTFLOW = " WYDATKI"
    CAT_CLOSING = " ZAMKNIĘCIE"

    def __init__(self):
        self.inflow_outflow_mapping = {
            MbankOperationType.PRZELEW_WEWNETRZNY_PRZYCHODZACY: self.CAT_INFLOW,
            MbankOperationType.PRZELEW_ZEWNETRZNY_PRZYCHODZACY: self.CAT_INFLOW,
            MbankOperationType.PRZELEW_SEPA_PRZYCHODZACY: self.CAT_INFLOW,
            MbankOperationType.PRZELEW_ZEWNETRZNY_WYCHODZACY: self.CAT_OUTFLOW,
            MbankOperationType.PRZELEW_WEWNETRZNY_WYCHODZACY: self.CAT_OUTFLOW,
            MbankOperationType.PRZELEW_SEPA_WYCHODZACY: self.CAT_OUTFLOW,
            MbankOperationType.PRZELEW_SORBNET_WYCHODZACY: self.CAT_OUTFLOW,
            MbankOperationType.PRZELEW_EXPRESS_ELIXIR_PRZYCH: self.CAT_OUTFLOW,
            MbankOperationType.PRZELEW_EXPRESSOWY_PRZELEW_PRZYCH: self.CAT_OUTFLOW,
            MbankOperationType.ZAKUP_PRZY_UZYCIU_KARTY: self.CAT_OUTFLOW,
            RevolutOperationType.CARD_PAYMENT: self.CAT_OUTFLOW,
            MbankOperationType.WYPLATA: self.CAT_OUTFLOW,
        }
        self.inflow_mapping = {
            MbankOperationType.PRZELEW_WEWNETRZNY_PRZYCHODZACY: self.CAT_INFLOW,
            MbankOperationType.PRZELEW_ZEWNETRZNY_PRZYCHODZACY: self.CAT_INFLOW,
            MbankOperationType.PRZELEW_SEPA_PRZYCHODZACY: self.CAT_INFLOW,
            # Revolut: zwrot z Robo / trading (From Robo portfolio) — Rodzaj Przelew|Transfer.
            RevolutOperationType.PRZELEW: self.CAT_INFLOW,
            RevolutOperationType.TRANSFER: self.CAT_INFLOW,
        }
        self.initial_investment_mapping = {
            MbankOperationType.PRZELEW_ZEWNETRZNY_WYCHODZACY: self.CAT_INVESTMENT,
            MbankOperationType.PRZELEW_WEWNETRZNY_WYCHODZACY: self.CAT_INVESTMENT,
            MbankOperationType.PRZELEW_SORBNET_WYCHODZACY: self.CAT_INVESTMENT,
            MbankOperationType.PRZELEW_SEPA_WYCHODZACY: self.CAT_INVESTMENT,
            MbankOperationType.PRZELEW_SEPA_PRZYCHODZACY: self.CAT_INVESTMENT,
            MbankOperationType.PRZELEW_WALUTOWY_PRZYCHODZACY: self.CAT_INVESTMENT,
            MbankOperationType.WYPLATA: self.CAT_INVESTMENT,
            # Zakupy złota kartą (mBank / Revolut).
            MbankOperationType.ZAKUP_PRZY_UZYCIU_KARTY: self.CAT_INVESTMENT,
            RevolutOperationType.CARD_PAYMENT: self.CAT_INVESTMENT,
            # Revolut: CAPEX do Robo / trading (To Robo portfolio).
            RevolutOperationType.PRZELEW: self.CAT_INVESTMENT,
            RevolutOperationType.TRANSFER: self.CAT_INVESTMENT,
        }
        self.investment_refund_mapping = {
            MbankOperationType.PRZELEW_WEWNETRZNY_PRZYCHODZACY: self.CAT_INVESTMENT,
        }
        self.closing_investment_mapping = {
            MbankOperationType.PRZELEW_WEWNETRZNY_PRZYCHODZACY: self.CAT_CLOSING,
            MbankOperationType.PRZELEW_ZEWNETRZNY_PRZYCHODZACY: self.CAT_CLOSING,
            RevolutOperationType.PRZELEW: self.CAT_CLOSING,
            RevolutOperationType.TRANSFER: self.CAT_CLOSING,
        }

    def add_ymd_columns(self, df):
        return add_ymd_columns(df)

    def check_values(self, _df: pd.DataFrame):
        df = _df.copy()
        for cat, df_group in df.groupby(self.CAT):
            pos = df_group[df_group[self.AMOUNT] >= 0.0]
            neg = df_group[df_group[self.AMOUNT] < 0.0]
            if cat in (self.CAT_INVESTMENT, self.CAT_OUTFLOW):
                if not pos.empty:
                    raise ExpectedNegativeValue(pos)
            elif cat in (self.CAT_INFLOW, self.CAT_CLOSING):
                if not neg.empty:
                    raise ExpectedPositiveValue(neg)
            else:
                raise NotImplementedError

    def create(self, data: list) -> pd.DataFrame:
        cols = (
            self.TRANSACTION_DATE,
            self.AMOUNT,
            self.CAT,
            self.OPERATION_TYPE,
        )
        r0 = pd.DataFrame(data=data, columns=cols)
        r0 = AssetRw.add_ymd_columns(r0)
        self.check_values(r0)
        return r0


AssetRw = AssetRWCls()
