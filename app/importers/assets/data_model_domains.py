# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from importers.data_model_generic import DomainCheckerGeneric


class GroupDomainCls(DomainCheckerGeneric):
    CASH = '0 środki pieniężne'
    DEPOSIT = '1 środki pieniężne'
    INVESTMENT = '5 inwestycje finansowe'
    PROPERTY = '9 nieruchomości'

    def domain(self) -> set:
        return {
            self.CASH,
            self.DEPOSIT,
            self.INVESTMENT,
            self.PROPERTY
        }


class CurrencyDomainCls(DomainCheckerGeneric):
    def domain(self):
        return {'EUR', 'PLN'}


class TypeDomainCls(DomainCheckerGeneric):
    CURRENT_ACCOUNT = 'ror'
    DEPOSIT = 'depozyt'
    EQUITIES = 'udziały'
    BONDS = 'obligacje'
    PROPERTY = 'property'

    def domain(self) -> set:
        return {
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
    REGNOLOGY = 'reg_import'

    def domain(self) -> set:
        return {
            self.MBANK + '.PM',
            self.MBANK + '.GM',
            self.REVOLUT + '.PM',
            self.REVOLUT + '.GM',
            self.ASSETS + '.IKE-GM',
            self.ASSETS + '.IKE-PM',
            self.BONDS,
            self.BROKER,
            self.REGNOLOGY,

            '?'
        }
