# -*- coding: utf-8 -*-
__author__ = 'Piotr'

from importers.data_model_generic import GenericStructureClass


class MBankFileCls(GenericStructureClass):
    MBANK_BOOKING_DATE = '#Data księgowania'
    MBANK_TRANSACTION_DATE = '#Data operacji'
    MBANK_DESCRIPTION = '#Opis operacji'
    MBANK_TITLE = '#Tytuł'
    MBANK_TRANSACTION_PARTY = '#Nadawca/Odbiorca'
    MBANK_ACCOUNT_NUMBER = '#Numer konta'
    MBANK_AMOUNT = '#Kwota'
    MBANK_OUTSTANDING_BALANCE = '#Saldo po operacji'

    EFFECTIVE_DATE = 'Data transakcji'
    DEBIT_ACCOUNT = 'Konto bazowe'
    # MBANK_TRANS_GUID = 'trans_guid'
    # MBANK_DATA_FILE = 'PLIK'

    def __init__(self):
        super().__init__()

    def expected_columns(self) -> set:
        result = {
            self.MBANK_BOOKING_DATE,
            self.MBANK_TRANSACTION_DATE,
            self.MBANK_DESCRIPTION,
            self.MBANK_TITLE,
            self.MBANK_TRANSACTION_PARTY,
            self.MBANK_ACCOUNT_NUMBER,
            self.MBANK_AMOUNT,
            self.MBANK_OUTSTANDING_BALANCE,

            # added
            self.EFFECTIVE_DATE,
            self.DEBIT_ACCOUNT,
            # MBANK_TRANS_GUID,
            # self.MBANK_DATA_FILE,
        }
        return result

    def unique_key(self) -> list:
        result = [
            self.MBANK_BOOKING_DATE,
            self.MBANK_TRANSACTION_DATE,
            self.MBANK_DESCRIPTION,
            self.MBANK_TITLE,
            self.MBANK_TRANSACTION_PARTY,
            self.MBANK_ACCOUNT_NUMBER,
            self.MBANK_AMOUNT,
            self.MBANK_OUTSTANDING_BALANCE,

            # added
            # self.MBANK_EFFECTIVE_DATE,
            # self.MBANK_DEBIT_ACCOUNT,
            # MBANK_TRANS_GUID,
            # self.MBANK_DATA_FILE,
        ]
        return result


MBankFile = MBankFileCls()


# DESCRIPTION VALUES
# CARD_PURCHASE = 'ZAKUP PRZY UŻYCIU KARTY'
# CARD_ATM_WITHDRAWAL = 'WYPŁATA W BANKOMACIE'
# INTEREST_TAX = 'PODATEK OD ODSETEK KAPITAŁOWYCH'

# ATM_WTHDRAWAL_FEE = 'PROWIZJA-WYPŁATA BANKOMAT KRAJOWY'
# ATM_ABROAD_WTHDRAWAL_FEE = 'PROWIZJA-WYPŁATA BANKOMAT ZAGRAN.'

    # 'POS ZWROT TOWARU': _card_payments,
    # 'RĘCZNA SPŁATA KARTY KREDYT.': _card_payments,
    # 'WYGAŚNIĘCIE LOKATY TERMINOWEJ': _card_payments,
    #
    # 'KAPITALIZACJA ODSETEK': _fees_payments,
    # 'ODSETKI LOKAT TERMINOWYCH': _fees_payments,
    # 'OPŁATA MIES. ZA POLECENIE ZAPŁATY': _fees_payments,
    # 'OPŁATA ZA WYPŁATĘ GOT. W KASIE': _fees_payments,
    # 'OPŁATA ZA KARTĘ': _fees_payments,
    # 'ZERWANIE LOKATY TERMINOWEJ': _fees_payments,
    # 'ZWROT OPłATY ZA UżYWANIE KARTY': _fees_payments,
    # 'OPŁATA-PRZELEW EKSPRESOWY': _fees_payments,
    # 'OPŁATA-PRZELEW WEWN. ZDEFINIOWANY': _fees_payments,
    #
    # 'BLIK ZAKUP E-COMMERCE': _blik_payments,
    # 'BLIK KOR. ZAKUPU E-COMMERCE': _blik_payments,
    # 'BLIK ZAKUP': _blik_payments,
    # 'BLIK WYPŁATA ATM KRAJOWY': _blik_payments,
    # 'BLIK ZAKUP NFC': _blik_payments,
    # 'BLIK ANUL. ZAKUPU NFC': _blik_payments,
    # 'BLIK P2P-PRZYCHODZĄCY': _blik_payments,
    # 'BLIK P2P-WYCHODZĄCY': _blik_payments,
    #
    # 'PRZELEW WŁASNY': iban_acc,
    # 'PRZELEW ZEWNĘTRZNY PRZYCHODZĄCY': iban_acc,
    # 'PRZELEW ZEWNĘTRZNY WYCHODZĄCY': iban_acc,
    # 'PRZELEW SEPA PRZYCHODZĄCY': iban_acc,
    # 'PRZELEW EKSPRESOWY': iban_acc,
    # 'PRZELEW WEWNĘTRZNY PRZYCHODZĄCY': iban_acc,
    # 'PRZELEW WEWNĘTRZNY WYCHODZĄCY': iban_acc,
    # 'PRZELEW MTRANSFER WYCHODZACY': iban_acc,
    # 'POLECENIE ZAPŁATY - OBCIĄŻENIE': iban_acc,
    # 'PRZELEW PODATKOWY': iban_acc,
    # 'PRZELEW ZEWNĘTRZNY DO ZUS': iban_acc,
BASE_ACCOUNT = 'Base account'


class MbankOperationTypeClass:
    PRZELEW_ZEWNETRZNY_PRZYCHODZACY = 'PRZELEW ZEWNĘTRZNY PRZYCHODZĄCY'
    PRZELEW_WEWNETRZNY_PRZYCHODZACY = 'PRZELEW WEWNĘTRZNY PRZYCHODZĄCY'

    PRZELEW_ZEWNETRZNY_WYCHODZACY = 'PRZELEW ZEWNĘTRZNY WYCHODZĄCY'
    PRZELEW_WEWNETRZNY_WYCHODZACY = 'PRZELEW WEWNĘTRZNY WYCHODZĄCY'

    PRZELEW_SORBNET_WYCHODZACY = 'PRZELEW SORBNET WYCHODZĄCY'
    PRZELEW_EXPRESSOWY_PRZELEW_PRZYCH = 'PRZELEW EXPRESSOWY PRZELEW PRZYCH.'
    PRZELEW_EXPRESS_ELIXIR_PRZYCH = 'PRZELEW EXPRESS ELIXIR PRZYCH.'


    ZAKUP_PRZY_UZYCIU_KARTY = 'ZAKUP PRZY UŻYCIU KARTY'
    PRZELEW_WLASNY = "PRZELEW WŁASNY"

    POLECENIE_ZAPLATY_OBCIAZENIE = 'POLECENIE ZAPŁATY - OBCIĄŻENIE'
    PRZELEW_MTRANSFER_WYCHODZACY = 'PRZELEW MTRANSFER WYCHODZACY'
    WYPLATA_W_BANKOMACIE = 'WYPŁATA W BANKOMACIE'
    ODSETKI_LOKAT_TERMINOWYCH = 'ODSETKI LOKAT TERMINOWYCH'
    PODATEK_OD_ODSETEK_KAPITALOWYCH = 'PODATEK OD ODSETEK KAPITAŁOWYCH'
    ZERWANIE_LOKATY_TERMINOWEJ = 'ZERWANIE LOKATY TERMINOWEJ'
    WYGASNIECIE_LOKATY_TERMINOWEJ = 'WYGAŚNIĘCIE LOKATY TERMINOWEJ'
    BLIK_ZAKUP_NFC = 'BLIK ZAKUP NFC'

    def __init__(self):
        self.values = {
            self.PRZELEW_MTRANSFER_WYCHODZACY,
            self.ZAKUP_PRZY_UZYCIU_KARTY,
            self.PRZELEW_ZEWNETRZNY_WYCHODZACY,
            self.PRZELEW_ZEWNETRZNY_PRZYCHODZACY,
            self.POLECENIE_ZAPLATY_OBCIAZENIE,
            self.WYPLATA_W_BANKOMACIE,
            self.PRZELEW_WEWNETRZNY_PRZYCHODZACY,
            self.BLIK_ZAKUP_NFC,
        }
        self.deposits_operations = {
            self.PRZELEW_WEWNETRZNY_WYCHODZACY,
            self.ODSETKI_LOKAT_TERMINOWYCH,
            self.PODATEK_OD_ODSETEK_KAPITALOWYCH,
            self.ZERWANIE_LOKATY_TERMINOWEJ,
            self.WYGASNIECIE_LOKATY_TERMINOWEJ,
        }


MbankOperationType = MbankOperationTypeClass()
