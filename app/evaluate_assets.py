# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

import pandas as pd

from mbank_importer.mbank_evaluate import mbank_evaluate


def evaluate_assets(my_data_path, assets: pd.DataFrame) -> pd.DataFrame:
    result = []

    a = assets[assets['rodzaj'].notnull()]
    for i, row in a.iterrows():
        if row['rodzaj'] == 'mbank_import':
            asset_id = row['id']
            r = mbank_evaluate(my_data_path, asset_id)
            result += [r]

    result = pd.concat(result)
    return result
