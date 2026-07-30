# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from importers.data_model_generic import GenericStructureClass


class RevolutAccountFileCls(GenericStructureClass):
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

    FILE_DATE = 'ref_date'

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
            self.BALANCE,
            self.FILE_DATE
        }
        return result

    def unique_key(self) -> list:
        result = [
            # self.KIND,
            self.PRODUCT,
            self.INIT_DATE,
            self.DATE,
            self.DESCRIPTION,
            self.AMOUNT,
            self.FEE,
            self.CURRENCY,
            self.STATE,
            self.BALANCE
        ]
        return result


RevolutAccountFile = RevolutAccountFileCls()


class RevolutOperationTypeClass:
    """Wartości kolumny Rodzaj (AccountTx.operation_type) z wyciągów Revolut."""

    CARD_PAYMENT = "Płatność kartą"
    TRANSFER = "Transfer"
    PRZELEW = "Przelew"


RevolutOperationType = RevolutOperationTypeClass()
