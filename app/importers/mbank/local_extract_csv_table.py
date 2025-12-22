# -*- coding: utf-8 -*-
__author__ = 'pmalczak@gmail.com'

import csv
from io import StringIO
from typing import Tuple

from importers.mbank.data_model import MBankFile


class ForbiddenSign(BaseException):
    pass


class WrongFileFormat(BaseException):
    pass


header = (f'{MBankFile.MBANK_BOOKING_DATE};{MBankFile.MBANK_TRANSACTION_DATE};{MBankFile.MBANK_DESCRIPTION};'
          f'{MBankFile.MBANK_TITLE};{MBankFile.MBANK_TRANSACTION_PARTY};{MBankFile.MBANK_ACCOUNT_NUMBER};'
          f'{MBankFile.MBANK_AMOUNT};{MBankFile.MBANK_OUTSTANDING_BALANCE}')


def extract_csv_table(f) -> Tuple[str, str, list]:
    base_account = ''
    ref_date = ''

    while True:
        line = f.readline()
        if line.startswith('#Numer rachunku'):
            base_account = f.readline()
            base_account = base_account[0:32]
            base_account = base_account.replace(' ', '')

        elif line.startswith('#Za okres'):
            ref_date = f.readline()
            ref_date = ref_date.split(';')
            assert len(ref_date) == 3
            ref_date = ref_date[1]
            ref_date = ref_date.split('.')
            assert len(ref_date) == 3
            ref_date = '-'.join(reversed(ref_date))
        #
        elif line.startswith(header):
            result = [line]
            result += _read_table_part(f)

            result = ''.join(result)
            str_io = StringIO(result)

            reader = csv.DictReader(str_io, delimiter=';', quotechar='"')
            result = list(reader)
            for line in result:
                for k, v in line.items():
                    if '"' in v:
                        m = f'pole:"{k}" treść:"{v}"'
                        raise ForbiddenSign(m)

            assert base_account != ''
            assert ref_date != ''
            return base_account, ref_date, result

        elif not line:
            raise WrongFileFormat


def _read_table_part(f) -> list:
    result = []
    while True:
        try:
            line = f.readline()
        except Exception:
            raise
        if line == ';;;;;;;\n':
            raise Exception("plik zmieniony przez Excel")
        if line == '\n':
            return result

        line = line.upper()
        result += [line]
