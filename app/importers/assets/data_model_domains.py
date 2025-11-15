# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from importers.data_model_generic import DomainCheckerGeneric


class GroupDomainCls(DomainCheckerGeneric):
    CASH = '0 gotówka'
    BANK_ACCOUNTS = '1 konta bankowe'
    DEPOSIT = '2 depozyty'
    INVESTMENT = '5 inwestycje finansowe'
    PROPERTY = '9 nieruchomości'

    def domain(self) -> set:
        return {
            self.CASH,
            self.BANK_ACCOUNTS,
            self.DEPOSIT,
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
    EQUITIES = 'udziały'
    BONDS = 'obligacje'
    PROPERTY = 'property'

    def domain(self) -> set:
        return {
            self.CASH,
            self.CURRENT_ACCOUNT,
            self.DEPOSIT,
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
            self.ASSETS + '.rocky-iv',
            self.ASSETS + '.cash',
            self.BONDS,
            self.BROKER,
            # self.REGNOLOGY,

            '?'
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
