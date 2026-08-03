# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from importers.data_model_generic import GenericStructureClass


class PkoBpBondsCls(GenericStructureClass):
    DATE = 'DATA DYSPOZYCJI'
    ORDER_TYPE = 'RODZAJ DYSPOZYCJI'
    CODE = 'KOD OBLIGACJI'
    NO_LINE = 'NR ZAPISU'
    SERIES = 'SERIA'
    BONDS_NO = 'LICZBA OBLIGACJI'
    AMOUNT = 'KWOTA OPERACJI'
    STAT = 'STATUS'
    NOTES = 'UWAGI'

    def expected_columns(self) -> set:
        return {
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


class PkoBpStanCls(GenericStructureClass):
    EMISSION = 'EMISJA'
    QTY_AVAILABLE = 'DOSTĘPNA LICZBA OBLIGACJI'
    QTY_BLOCKED = 'ZABLOKOWANA LICZBA OBLIGACJI'
    NOMINAL = 'WARTOŚĆ NOMINALNA'
    CURRENT_VALUE = 'WARTOŚĆ AKTUALNA'
    MATURITY = 'DATA WYKUPU'
    UNIT_PRICE = 'unit_price'
    FILE_DATE = 'FILE_DATE'

    def expected_columns(self) -> set:
        return {
            self.EMISSION,
            self.QTY_AVAILABLE,
            self.QTY_BLOCKED,
            self.NOMINAL,
            self.CURRENT_VALUE,
            self.MATURITY,
            self.UNIT_PRICE,
            self.FILE_DATE,
        }

    def source_columns(self) -> set:
        """Kolumny z Excela (bez wyliczanych)."""
        return {
            self.EMISSION,
            self.QTY_AVAILABLE,
            self.QTY_BLOCKED,
            self.NOMINAL,
            self.CURRENT_VALUE,
            self.MATURITY,
        }


PkoBpBonds = PkoBpBondsCls()
PkoBpStan = PkoBpStanCls()

# Rejestr: operacje na papierach (inventory qty)
PAPER_BUY_TYPES = frozenset({'dyspozycja zakupu'})
PAPER_SELL_TYPES = frozenset({
    'wykup papierów',
    'dyspozycja przedterminowego wykupu',
})
QTY_BUY_TYPES = PAPER_BUY_TYPES
QTY_SELL_TYPES = PAPER_SELL_TYPES
QTY_ORDER_TYPES = QTY_BUY_TYPES | QTY_SELL_TYPES

# Rejestr: operacje na rachunku pieniężnym (poza ROI per kod)
CASH_ACCOUNT_TYPES = frozenset({
    'przedterminowy wykup',
    'przelew z rachunku',
})

# Rejestr: przepływy pieniężne — jedyne źródło cashflow ROI
CASHFLOW_EXACT_TYPES = frozenset({
    'zakup papierów',
    'podatek',
    'wypłata przelewem',
    'odsetki',
    'opłata za przedterminowy wykup',
    'wykup - odsetki',
})
CASHFLOW_PREFIX_TYPES = ('naliczenie odsetek na ',)

# Znaki KWOTA OPERACJI w 01 source — kierunek zmiany wartości instrumentu:
# CAPEX / REVENUES (zwiększa) → ujemne; OPEX / DIVESTMENT (zmniejsza) → dodatnie.
AMOUNT_NEGATIVE_TYPES = frozenset({
    'zakup papierów',  # CAPEX
    'wykup - odsetki',  # REVENUES
    'odsetki',  # REVENUES
})
AMOUNT_NEGATIVE_PREFIXES = ('naliczenie odsetek na ',)  # REVENUES
AMOUNT_POSITIVE_TYPES = frozenset({
    'podatek',  # OPEX
    'wypłata przelewem',  # DIVESTMENT
    'opłata za przedterminowy wykup',  # OPEX
})

# Uzupełnienia ręczne brakujących wypłat (dołączane przy imporcie historii).
# Data OTS1019: 2019-10-08 (w komunikacie było 2010 — korektura do serii OTS1019).
MANUAL_CASHFLOW_ROWS = (
    {
        PkoBpBonds.DATE: '2019-09-24',
        PkoBpBonds.ORDER_TYPE: 'wypłata przelewem',
        PkoBpBonds.CODE: 'OTS0919',
        PkoBpBonds.NO_LINE: 0,
        PkoBpBonds.SERIES: None,
        PkoBpBonds.BONDS_NO: 0,
        PkoBpBonds.AMOUNT: -10030.78,
        PkoBpBonds.STAT: 'zrealizowana',
        PkoBpBonds.NOTES: 'manual',
    },
    {
        PkoBpBonds.DATE: '2019-10-08',
        PkoBpBonds.ORDER_TYPE: 'wypłata przelewem',
        PkoBpBonds.CODE: 'OTS1019',
        PkoBpBonds.NO_LINE: 0,
        PkoBpBonds.SERIES: None,
        PkoBpBonds.BONDS_NO: 0,
        PkoBpBonds.AMOUNT: -20061.56,
        PkoBpBonds.STAT: 'zrealizowana',
        PkoBpBonds.NOTES: 'manual',
    },
)


def is_cashflow_register(order_type: str) -> bool:
    t = str(order_type).strip()
    if t in CASHFLOW_EXACT_TYPES:
        return True
    return any(t.startswith(prefix) for prefix in CASHFLOW_PREFIX_TYPES)


def normalized_cashflow_amount(order_type: str, amount: float) -> float:
    """Idempotentna normalizacja znaku kwoty do konwencji ROI obligacji."""
    t = str(order_type).strip()
    value = float(amount)
    if t in AMOUNT_NEGATIVE_TYPES or any(t.startswith(p) for p in AMOUNT_NEGATIVE_PREFIXES):
        return -abs(value)
    if t in AMOUNT_POSITIVE_TYPES:
        return abs(value)
    return value
