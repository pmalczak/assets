# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from importers.pkobp.data_model import PkoBpBonds


def import_bonds(input_path: Path = None) -> pd.DataFrame:
    input_files = list(input_path.glob('*.xls'))

    result = []
    for input_file in input_files:
        try:
            transactions = pd.read_excel(input_file)
            PkoBpBonds.check_structure(transactions)
        except Exception as e:
            raise

        print(f'PLIK:{input_file} {len(transactions):>4} rekord/ów')
        transactions = transactions[transactions[PkoBpBonds.STAT] == 'zrealizowana']
        transactions = transactions[transactions[PkoBpBonds.CODE] != 'TZ0208']

        result += [transactions]

    result = pd.concat(result)
    result = _select_working_(result)
    return result


def _select_working_(transactions: pd.DataFrame):
    cond_ = transactions[PkoBpBonds.ORDER_TYPE].isin(
        ('wykup papierów', 'zakup papierów', 'dyspozycja przedterminowego wykupu'))
    operacje_na_papierach = transactions[cond_].drop(columns=[PkoBpBonds.AMOUNT, 'UWAGI', PkoBpBonds.STAT])
    c = operacje_na_papierach[PkoBpBonds.ORDER_TYPE].isin(('wykup papierów', 'dyspozycja przedterminowego wykupu'))
    operacje_na_papierach.loc[c, 'LICZBA OBLIGACJI'] = - operacje_na_papierach.loc[c, 'LICZBA OBLIGACJI']
    pracujace_obligacje = pd.pivot_table(operacje_na_papierach,
                                         index=[PkoBpBonds.CODE],  # , 'SERIA'],
                                         columns=PkoBpBonds.ORDER_TYPE, values='LICZBA OBLIGACJI',
                                         aggfunc='sum')
    pracujace_obligacje = pracujace_obligacje.fillna(0).astype('int')
    pracujace_obligacje['LICZBA OBLIGACJI'] = pracujace_obligacje.sum(axis=1)
    pracujace_obligacje = pracujace_obligacje[pracujace_obligacje['LICZBA OBLIGACJI'] != 0]
    pracujace_obligacje = pracujace_obligacje.reset_index()
    pracujace_obligacje = pracujace_obligacje[[PkoBpBonds.CODE]]

    # toz0822 = operacje_na_papierach[operacje_na_papierach['KOD OBLIGACJI'] == 'TOZ0822']
    # transactions = transactions[~cond_]
    result = pd.merge(transactions, pracujace_obligacje, on=PkoBpBonds.CODE)
    result = result[result[PkoBpBonds.ORDER_TYPE] == 'zakup papierów']
    return result
