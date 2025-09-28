# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from assets.data_model import GenericAsset


class PkoBpBondsCls(GenericAsset):
    DATE = 'DATA DYSPOZYCJI'
    ORDER_TYPE = 'RODZAJ DYSPOZYCJI'
    CODE = 'KOD OBLIGACJI'
    NO_LINE = 'NR ZAPISU'
    SERIES = 'SERIA'
    BONDS_NO = 'LICZBA OBLIGACJI'
    AMOUNT = 'KWOTA OPERACJI'
    STAT = 'STATUS'
    NOTES = 'UWAGI'

    def __init__(self):
        super().__init__()

    def expected_columns(self) -> set:
        result = {
            self.DATE,
            self.ORDER_TYPE,
            self.CODE,
            self.NO_LINE,
            self.SERIES,
            self.BONDS_NO,
            self.AMOUNT,
            self.STAT,
            self.NOTES,
        }
        return result


PkoBpBonds = PkoBpBondsCls()
