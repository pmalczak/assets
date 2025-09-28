# -*- coding: utf-8 -*-
__author__ = 'pmalczak@gmail.com'

import pandas as pd
from pathlib import Path
from io import StringIO
import platform

from .data_model import MBankFile
from .local_extract_csv_table import extract_csv_table


def read_mbank_csv_file(input_file: Path) -> pd.DataFrame:
    sys = platform.system()
    if sys == 'Linux':
        arg = {'encoding': 'Windows-1250'}
    elif sys == 'Windows':
        arg = {}
    else:
        raise ValueError(sys)
    with open(input_file, 'r', **arg) as f:   # , encoding='Windows-1250'
        in_content = f.read()

        in_content = in_content.replace('""SKY MARCHE" ', '"SKY MARCHE ')
        in_content = in_content.replace('""PIJ""', '"PIJ"')
        in_content = in_content.replace('""PIJ" ', '"PIJ')
        in_content = in_content.replace('""Super-Sam" ', '"Super-Sam')
        in_content = in_content.replace('""VISION" ', '"VISION ')
        in_content = in_content.replace('""MADEX" ', '"MADEX ')
        in_content = in_content.replace('""VIET-THAI" ', '"VIET-THAI ')
        in_content = in_content.replace('"Salon " GRENO HOME', '"Salon  GRENO HOME')
        in_content = in_content.replace('Hala "Tecza" ', 'Hala Tecza ')
        in_content = in_content.replace('"HALA "TECZA""', '"HALA TECZA"')
        in_content = in_content.replace('""BIALY DOMEK CAFE""', '"BIALY DOMEK CAFE"')
        in_content = in_content.replace('"APTEKA "BEATA""', '"APTEKA BEATA"')
        in_content = in_content.replace('""SUPER-SAM""', '"SUPER-SAM"')
        in_content = in_content.replace('""Alkohol, Kawa, Her', '"Alkohol, Kawa, Her')
        in_content = in_content.replace('"Sklep "AGD" ', '"Sklep AGD ')
        #

        str_io = StringIO(in_content)
        base_account, result = extract_csv_table(str_io)

    result = pd.DataFrame(result)
    result = result.drop(columns=[''])

    result[MBankFile.MBANK_DATA_FILE] = str(input_file)
    result[MBankFile.MBANK_EFFECTIVE_DATE] = result.apply(_effective_date, axis=1)
    result[MBankFile.MBANK_DEBIT_ACCOUNT] = base_account
    result[MBankFile.MBANK_ACCOUNT_NUMBER] = result[MBankFile.MBANK_ACCOUNT_NUMBER].apply(_clear_brackets_)
    result[MBankFile.MBANK_AMOUNT] = result[MBankFile.MBANK_AMOUNT].apply(_as_float_)
    result[MBankFile.MBANK_OUTSTANDING_BALANCE] = result[MBankFile.MBANK_OUTSTANDING_BALANCE].apply(_as_float_)

    MBankFile.check_structure(result)
    return result


def _as_float_(x: str) -> float:
    result = x.replace(' ', '')
    result = result.replace(',', '.')
    return float(result)


def _clear_brackets_(x):
    if len(x) == 0:
        return x

    if x[0] == "'":
        if x[-1] == "'":
            return x[1:-1]
    raise ValueError(x)


def _effective_date(record):
    result = record[MBankFile.MBANK_TRANSACTION_DATE]
    title = record[MBankFile.MBANK_TITLE]
    idx = title.find('DATA TRANSAKCJI:')
    if idx >= 0:
        result = title[(idx + 17):]
    return result
