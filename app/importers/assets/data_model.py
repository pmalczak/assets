# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

import pandas as pd

from importers.assets.data_model_domains import GroupDomainCls, CurrencyDomainCls, TypeDomainCls, KindDomainCls, \
    OperationDomainCls, TitleMatchDomainCls
from importers.data_model_generic import GenericStructureClass


class AssetsFileCls(GenericStructureClass):
    ID = 'id'
    TYPE = 'typ'
    GROUP = 'grupa'
    DESCR = 'opis'
    KIND = 'RODZAJ*'
    CURRENCY = 'waluta'
    NOTES = 'dostęp'
    # pool_id jest kolumną runtime (assign_pool_id), nie częścią Excela.
    POOL_ID = "pool_id"

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
            self.NOTES,
        }
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
    DAYS_AFTER_VALUATION = 'liczba dni od wyceny'
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
        # Odrzuć kolumny runtime (np. pool_id z read_assets), spoza schematu AssetsDef.
        extras = [key for key in result.index if key not in self.expected_columns()]
        if extras:
            result = result.drop(labels=extras)
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


class PropertyValuationsCls(PropertiesCls):
    """Arkusz asset-evaluation — te same kolumny co Properties (id, Data, wartosc, metraz, operacja)."""

    pass


PropertyValuations = PropertyValuationsCls()


class InventoryCls(GenericStructureClass):
    """Inventory zakupow: data + instrument + waga + sztuki (bez matchu bankowego)."""

    DATE = 'Data'
    INSTRUMENT = 'instrument'
    WEIGHT = 'waga'
    QUANTITY = 'sztuki'
    NOTES = 'notatki'

    def expected_columns(self) -> set:
        return {
            self.DATE,
            self.INSTRUMENT,
            self.WEIGHT,
            self.QUANTITY,
        }

    def check_structure(self, df: pd.DataFrame, file=None):
        """Wymaga Data/instrument/waga/sztuki; notatki i inne kolumny opcjonalne."""
        del file
        missing = self.expected_columns() - set(df.columns)
        if missing:
            raise ValueError(missing)


class PurchaseRulesCls(GenericStructureClass):
    """Legacy schema — tylko testy / match_bank_transaction (nie arkusz assets_1)."""

    RULE_ID = 'rule_id'
    SOURCE_ACCOUNT = 'konto_źródłowe'
    DATE = 'data'
    DATE_FROM = 'data_od'
    DATE_TO = 'data_do'
    TITLE = 'tytuł'
    TITLE_MATCH = 'tytuł_dopasowanie'
    COUNTERPARTY = 'kontrahent'
    COUNTERPARTY_IBAN = 'iban_kontrahenta'
    AMOUNT = 'kwota'
    AMOUNT_TOLERANCE = 'tolerancja_kwoty'
    OPERATION_DESCRIPTION = 'opis_operacji'
    INSTRUMENT = InventoryCls.INSTRUMENT
    QUANTITY = InventoryCls.QUANTITY
    WEIGHT = InventoryCls.WEIGHT
    NOTES = InventoryCls.NOTES

    def expected_columns(self) -> set:
        return {
            self.RULE_ID,
            self.SOURCE_ACCOUNT,
            self.DATE,
            self.DATE_FROM,
            self.DATE_TO,
            self.TITLE,
            self.TITLE_MATCH,
            self.COUNTERPARTY,
            self.COUNTERPARTY_IBAN,
            self.AMOUNT,
            self.AMOUNT_TOLERANCE,
            self.OPERATION_DESCRIPTION,
            self.INSTRUMENT,
            self.QUANTITY,
            self.WEIGHT,
            self.NOTES,
        }

    def check_structure(self, df: pd.DataFrame, file=None):
        super().check_structure(df, file=file)
        if df.empty:
            return
        TitleMatchDomain.is_in_domain(
            df[df[self.TITLE_MATCH].notna()],
            file=file,
        )


class UnitPriceEvaluationCls(GenericStructureClass):
    """Arkusz cen jednostkowych instrumentow (mark-to-market ROI / snapshot)."""

    DATE = 'Data'
    INSTRUMENT = InventoryCls.INSTRUMENT
    UNIT_PRICE = 'cena_jednostkowa'
    NOTES = 'notatki'

    def expected_columns(self) -> set:
        return {
            self.DATE,
            self.INSTRUMENT,
            self.UNIT_PRICE,
            self.NOTES,
        }


Inventory = InventoryCls()
PurchaseRules = PurchaseRulesCls()
UnitPriceEvaluation = UnitPriceEvaluationCls()
TitleMatchDomain = TitleMatchDomainCls(PurchaseRules.TITLE_MATCH)

INVENTORY_SHEET = 'inventory'
UNIT_PRICE_EVALUATION_SHEET = 'unit-price-evaluation'
ASSET_EVALUATION_SHEET = 'asset-evaluation'
LEGACY_INVENTORY_SHEET = 'zloto-monety-zakupy'
LEGACY_UNIT_PRICE_EVALUATION_SHEET = 'zloto-monety-wyceny'
LEGACY_ASSET_EVALUATION_SHEET = 'properties-wyceny'
LEGACY_PROPERTIES_SHEET = 'properties'
