# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

import pandas as pd

from data_step.data_step import DATA_STEP
from mbank_importer.mbank_evaluate import mbank_evaluate


def evaluate_assets(data_root, assets: pd.DataFrame) -> pd.DataFrame:
    r = DATA_STEP.obtain('assets_valuation.parquet', _evaluate_assets,
                         data_root=data_root, assets=assets)
    return r.data_frame()


def _evaluate_assets(data_root = None, assets: pd.DataFrame = None) -> pd.DataFrame:
    result = []

    a = assets[assets['rodzaj'].notnull()]
    for i, row in a.iterrows():
        if row['rodzaj'] == 'mbank_import':
            asset_id: str = row['id']
            r = mbank_evaluate(data_root, asset_id)
            result += [r]

    result = pd.concat(result)
    return result
