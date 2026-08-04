# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

import pandas as pd

from importers.data_model_generic import GenericStructureClass
from .account_data_model import RevolutAccountFile

PERIOD_START = "period_start"
PERIOD_END = "period_end"


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
    FILE_DATE = RevolutAccountFile.FILE_DATE
    PERIOD_START = PERIOD_START
    PERIOD_END = PERIOD_END

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
            self.FILE_DATE,
            self.PERIOD_START,
            self.PERIOD_END,
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
        """UUID EN deposit CSV (legacy). Prefer savings-statement dla nowych importów."""
        df = _df.copy()
        df[RevolutDepositFile.DATE] = pd.to_datetime(df[RevolutDepositFile.COMPLETED_DATE], format="%d %b %Y")
        df[RevolutDepositFile.DATE] = df[RevolutDepositFile.DATE].dt.strftime("%Y-%m-%d")

        balance_text = df[RevolutDepositFile.DEP_BALANCE].astype(str)
        all_have_euro = balance_text.str.contains("€", regex=False).all()
        all_have_pln = balance_text.str.contains("PLN", regex=False).all()
        if all_have_euro and not all_have_pln:
            df[RevolutDepositFile.CURRENCY] = "eur"
            df[RevolutDepositFile.BALANCE] = (
                balance_text
                .replace({'€': '', ',': ''}, regex=True)
                .astype(float)
            )
        elif all_have_pln and not all_have_euro:
            df[RevolutDepositFile.CURRENCY] = "pln"
            from importers.revolut.savings_statement import parse_pl_amount
            df[RevolutDepositFile.BALANCE] = balance_text.map(parse_pl_amount).astype(float)
        else:
            raise ValueError("UUID deposit: nierozpoznana lub mieszana waluta w Balance")

        df[RevolutDepositFile.PERIOD_START] = ""
        df[RevolutDepositFile.PERIOD_END] = ""
        return df


RevolutDepositFile = RevolutDepositFileCls()
