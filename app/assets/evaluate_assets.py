# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

import pandas as pd
from data_step.data_step import DATA_STEP
from importers.evaluate_mbank import evaluate_mbank
from importers.evaluate_regnology import evaluate_regnology
from importers.evaluate_revolut import evaluate_revolut


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
        elif rodzaj_importu == 'reg_import':
            asset_id: str = row['id']
            r = evaluate_regnology(data_root, asset_id)
            result += [r]
            # read_revolut_transactions
        else:
            print(f'brakujący typ: {rodzaj_importu}')


    result = pd.concat(result)
    return result
