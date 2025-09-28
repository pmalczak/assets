# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from assets.data_model import GenericAsset


class RevolutFileCls(GenericAsset):
    KIND = 'Rodzaj'
    PRODUCT = 'Produkt'
    INIT_DATE = 'Data rozpoczęcia'
    DATE = 'Data zrealizowania'
    DESCRIPTION = 'Opis'
    AMOUNT = 'Kwota'
    BALANCE = 'Saldo'
    FEE = 'Opłata'
    CURRENCY = 'Waluta'
    STATE = 'State'

    def __init__(self):
        super().__init__()

    def expected_columns(self) -> set:
        result = {
            self.KIND,
            self.PRODUCT,
            self.INIT_DATE,
            self.DATE,
            self.DESCRIPTION,
            self.AMOUNT,
            self.FEE,
            self.CURRENCY,
            self.STATE,
            self.BALANCE
        }
        return result


RevolutFile = RevolutFileCls()
