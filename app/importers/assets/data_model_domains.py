# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from importers.data_model_generic import DomainCheckerGeneric


class GroupDomainCls(DomainCheckerGeneric):
    CASH = '0 gotówka'
    BANK_ACCOUNTS = '1 konta bankowe'
    DEPOSIT = '2 depozyty'
    GOLD_COINS = '3 złoto-monety'
    INVESTMENT = '5 inwestycje finansowe'
    PROPERTY = '9 nieruchomości'

    def domain(self) -> set:
        return {
            self.CASH,
            self.BANK_ACCOUNTS,
            self.DEPOSIT,
            self.GOLD_COINS,
            self.INVESTMENT,
            self.PROPERTY
        }


class CurrencyDomainCls(DomainCheckerGeneric):
    def domain(self):
        return {'EUR', 'PLN'}


class TypeDomainCls(DomainCheckerGeneric):
    CASH = 'cash'
    CURRENT_ACCOUNT = 'ror'
    DEPOSIT = 'depozyt'
    GOLD_COINS = 'złoto-monety'
    EQUITIES = 'udziały'
    BONDS = 'obligacje'
    PROPERTY = 'property'

    def domain(self) -> set:
        return {
            self.CASH,
            self.CURRENT_ACCOUNT,
            self.DEPOSIT,
            self.GOLD_COINS,
            self.EQUITIES,
            self.BONDS,
            self.PROPERTY
        }


class KindDomainCls(DomainCheckerGeneric):
    MBANK = 'mbank'
    REVOLUT = 'revolut'
    ASSETS = 'assets'
    BONDS = 'obligacje_skarbowe_import'
    BROKER = 'BROKER'
    # REGNOLOGY = 'reg_import'

    def domain(self) -> set:
        return {
            self.MBANK + '.PM',
            self.MBANK + '.GM',
            self.REVOLUT + '.PM',
            self.REVOLUT + '.GM',
            self.ASSETS + '.IKE-GM',
            self.ASSETS + '.IKE-PM',
            self.ASSETS + '.properties',
            self.ASSETS + '.properties-wyceny',
            self.ASSETS + '.rocky-iv',
            self.ASSETS + '.cash',
            self.ASSETS + '.zloto-monety',
            self.BONDS,
            self.BROKER,
            # self.REGNOLOGY,

            '?'
        }


class TitleMatchDomainCls(DomainCheckerGeneric):
    EXACT = 'exact'
    CONTAINS = 'contains'
    REGEX = 'regex'

    def domain(self) -> set:
        return {
            self.EXACT,
            self.CONTAINS,
            self.REGEX,
        }


class OperationDomainCls(DomainCheckerGeneric):
    SOLD = 'sprzedane'
    BUY = 'zakup'
    EVALUATION = 'wycena'

    def domain(self) -> set:
        return {
            self.SOLD,
            self.BUY,
            self.EVALUATION,
        }
