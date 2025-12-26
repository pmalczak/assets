# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

import pandas as pd

from importers.data_model_generic import GenericStructureClass
from importers.revolut.revolut_account_file import RevolutAccountFile


class RevolutDepositFileCls(GenericStructureClass):
    COMPLETED_DATE = 'Completed Date'
    PRODUCT_NAME = 'Product name'
    DESCRIPTION = 'Description'
    MONEY_OUT = 'Money out'
    MONEY_IN = 'Money in'
    DEP_BALANCE = 'Balance'

    DATE = RevolutAccountFile.DATE
    BALANCE = RevolutAccountFile.BALANCE
    CURRENCY = RevolutAccountFile.CURRENCY

    def __init__(self):
        super().__init__()

    def expected_columns(self) -> set:
        result = {
            self.COMPLETED_DATE,
            self.PRODUCT_NAME,
            self.DESCRIPTION,
            self.MONEY_OUT,
            self.MONEY_IN,
            self.DEP_BALANCE,

            self.DATE,
            self.BALANCE,
            self.CURRENCY,
        }
        return result

    def unique_key(self) -> list:
        result = [
            self.COMPLETED_DATE,
            # self.PRODUCT_NAME,
            self.DESCRIPTION,
            # self.MONEY_OUT,
            # self.MONEY_IN,
            self.DEP_BALANCE
        ]
        return result


    def normalize_dtypes(self, _df: pd.DataFrame) -> pd.DataFrame:
        df = _df.copy()
        df[RevolutDepositFile.DATE] = pd.to_datetime(df[RevolutDepositFile.COMPLETED_DATE], format="%d %b %Y")
        df[RevolutDepositFile.DATE] = df[RevolutDepositFile.DATE].dt.strftime("%Y-%m-%d")

        all_have_euro = df[RevolutDepositFile.DEP_BALANCE].astype(str).str.startswith("€").all()
        if not all_have_euro:
            raise ValueError
        df[RevolutDepositFile.CURRENCY] = "eur"

        df[RevolutDepositFile.BALANCE] = (
            df[RevolutDepositFile.DEP_BALANCE]
            .replace({'€': '', ',': ''}, regex=True)
            .astype(float)
        )
        return df


RevolutDepositFile = RevolutDepositFileCls()
