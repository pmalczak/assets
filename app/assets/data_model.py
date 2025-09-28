# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

import pandas as pd


class GenericAsset:
    def __init__(self):
        return

    def expected_columns(self) -> set:
        raise NotImplementedError

    def check_structure(self, df: pd.DataFrame):
        cols = df.columns.tolist()
        cols = set(cols)
        diff = cols.symmetric_difference(self.expected_columns())
        if diff:
            raise ValueError(diff)


class AssetsFileCls(GenericAsset):
    ID = 'id'
    TYPE = 'typ'
    GROUP = 'grupa'
    DESCR = 'opis'
    KIND = 'RODZAJ*'
    CURRENCY = 'waluta'
    NOTES = 'dostęp'

    def __init__(self):
        super().__init__()

    def expected_columns(self) -> set:
        required = {
            self.ID,
            self.TYPE,
            self.GROUP,
            self.DESCR,
            self.KIND,
            self.CURRENCY,
            self.NOTES}
        return required

AssetsFile = AssetsFileCls()


class AssetsCls(AssetsFileCls):
    EVALUATION_DATE = 'data wyceny'
    VALUE = 'wartość'
    IBAN = 'IBAN'

    def __init__(self):
        super().__init__()
        return

    def expected_columns(self) -> set:
        result = super().expected_columns() | {self.EVALUATION_DATE, self.VALUE, self.IBAN }
        return result

    def as_assets_row(self, rec):
        result = rec.copy()
        result[self.IBAN] = ''
        result[self.EVALUATION_DATE] = None
        result[self.VALUE] = 0.0
        return result


AssetsDef = AssetsCls()
