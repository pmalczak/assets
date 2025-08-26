# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"
from pathlib import Path
import pandas as pd
from data_step.data_step import DATA_STEP
from mbank_importer.evaluate_mbank import evaluate_mbank, m_rec_as_asset, r_rec_as_asset
from revolut_importer.read_r_transactions import read_revolut_transactions


def evaluate_assets(data_root, assets: pd.DataFrame) -> pd.DataFrame:
    r = DATA_STEP.obtain('assets_valuation.parquet', _evaluate_assets, data_root=data_root, assets=assets)
    return r.data_frame()


def _evaluate_assets(data_root = None, assets: pd.DataFrame = None) -> pd.DataFrame:
    result = []

    a = assets[assets['rodzaj'].notnull()]
    for i, row in a.iterrows():
        rodzaj_importu = row['rodzaj']
        if rodzaj_importu == 'mbank_import':
            asset_id: str = row['id']
            r = evaluate_mbank(data_root, asset_id)
            result += [r]

        elif rodzaj_importu == 'revolut_import':
            asset_id: str = row['id']
            r = evaluate_revolut(data_root, asset_id)
            result += [r]
            # read_revolut_transactions
        else:
            print(f'brakujący typ: {rodzaj_importu}')


    result = pd.concat(result)
    return result


def evaluate_revolut(data_root: Path = None, asset_id: str = None):
    p = data_root / asset_id
    if not p.is_dir():
        raise ValueError(p)
    df = read_revolut_transactions(p, asset_id)
    last =df[-1:]
    for i, row in last.iterrows():
        iban = ''  #row[MBANK_DEBIT_ACCOUNT]
        value = row['Saldo']
        d = r_rec_as_asset(row, asset_id, value, iban)
        break
    data = [d]
    df_m_23 = pd.DataFrame(data=data)
    return df_m_23
