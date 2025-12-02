# -*- coding: utf-8 -*-
__author__ = 'pmalczak@gmail.com'

import csv
from io import StringIO
from typing import Tuple


class ForbiddenSign(BaseException):
    pass


class NoData(BaseException):
    pass


class WrongFileFormat(BaseException):
    pass


def extract_csv_table(f) -> Tuple[str, list]:
    header = f'#Data księgowania;#Data operacji;#Opis operacji;#Tytuł;#Nadawca/Odbiorca;#Numer konta;' \
             '#Kwota;#Saldo po operacji'
    base_account = ''
    while True:
        line = f.readline()
        if line.startswith('#Numer rachunku'):
            base_account = f.readline()

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

            assert base_account is not None
            base_account = base_account[0:32]
            base_account = base_account.replace(' ', '')

            if len(result) == 0:
                raise NoData
            return base_account, result

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
