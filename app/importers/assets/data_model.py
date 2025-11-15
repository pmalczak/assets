# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

import pandas as pd

from importers.assets.data_model_domains import GroupDomainCls, CurrencyDomainCls, TypeDomainCls, KindDomainCls, \
    OperationDomainCls
from importers.data_model_generic import GenericStructureClass


class AssetsFileCls(GenericStructureClass):
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

    def check_structure(self, df: pd.DataFrame, file=None):
        super().check_structure(df)
        GroupDomain.is_in_domain(df)
        TypeDomain.is_in_domain(df)
        CurrencyDomain.is_in_domain(df)
        KindDomain.is_in_domain(df)


class AssetsCls(AssetsFileCls):
    EVALUATION_DATE = 'data wyceny'
    VALUE = 'wartość'
    VALUE_PLN = 'wartość-pln'
    VALUE_DATE = 'data-waluty'
    IBAN = 'IBAN'

    def __init__(self):
        super().__init__()
        return

    def expected_columns(self) -> set:
        result = (super().expected_columns() |
                  {self.EVALUATION_DATE, self.VALUE,
                   self.IBAN })
        return result

    def as_assets_row(self, rec):
        result = rec.copy()
        result[self.IBAN] = ''
        result[self.EVALUATION_DATE] = None
        result[self.VALUE] = 0.0
        return result


AssetsFile = AssetsFileCls()
AssetsDef = AssetsCls()
GroupDomain = GroupDomainCls(AssetsFile.GROUP)
CurrencyDomain = CurrencyDomainCls(AssetsFile.CURRENCY)
TypeDomain = TypeDomainCls(AssetsFile.TYPE)
KindDomain = KindDomainCls(AssetsFile.KIND)


class PropertiesCls(GenericStructureClass):
    ID = AssetsDef.ID
    DATE = 'Data'
    VALUE = AssetsDef.VALUE
    CURRENCY = AssetsDef.CURRENCY
    SIZE = 'metraż'
    OPERATION = 'operacja'
    UNIT_PRICE = 'cena za metr'

    def expected_columns(self) -> set:
        required = {
            self.ID,
            self.DATE,
            self.VALUE,
            self.CURRENCY,
            self.SIZE,
            self.OPERATION,
            self.UNIT_PRICE,
        }
        return required

    def check_structure(self, df: pd.DataFrame, file=None):
        super().check_structure(df)
        OperationDomain.is_in_domain(df, file=file)


Properties = PropertiesCls()

OperationDomain = OperationDomainCls(Properties.OPERATION)
