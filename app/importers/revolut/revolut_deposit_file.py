# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

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


RevolutDepositFile = RevolutDepositFileCls()
