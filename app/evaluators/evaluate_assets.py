# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

import pandas as pd
from data_step.data_step import DATA_STEP
from assets.data_model import AssetsDef
from evaluators.evaluate_mbank import evaluate_mbank
from evaluators.evaluate_obigacjeskarbowe import evaluate_obligacjeskarbowe
from evaluators.evaluate_regnology import evaluate_regnology
from evaluators.evaluate_revolut import evaluate_revolut


def evaluate_assets(data_root, assets: pd.DataFrame) -> pd.DataFrame:
    r = DATA_STEP.obtain('02 evaluated/assets.parquet', _evaluate_assets, data_root=data_root, assets=assets)
    return r.data_frame()


def _evaluate_assets(data_root = None, assets: pd.DataFrame = None) -> pd.DataFrame:
    result = []

    a = assets[assets[AssetsDef.KIND].notnull()]
    for i, assets_file_row in a.iterrows():
        assert isinstance(assets_file_row, pd.Series)
        rodzaj_importu: str = assets_file_row[AssetsDef.KIND]

        if rodzaj_importu == 'mbank_import':
            asset_id: str = assets_file_row[AssetsDef.ID]
            r = evaluate_mbank(data_root, asset_id, assets_file_row)
            AssetsDef.check_structure(r)
            result += [r]

        elif rodzaj_importu == 'revolut_import':
            asset_id: str = assets_file_row[AssetsDef.ID]
            r = evaluate_revolut(data_root, asset_id, assets_file_row)
            AssetsDef.check_structure(r)
            result += [r]

        elif rodzaj_importu == 'reg_import':
            asset_id: str = assets_file_row[AssetsDef.ID]
            r = evaluate_regnology(data_root, asset_id, assets_file_row)
            AssetsDef.check_structure(r)
            result += [r]

        elif rodzaj_importu == 'obligacje_skarbowe_import':
            asset_id: str = assets_file_row[AssetsDef.ID]
            r = evaluate_obligacjeskarbowe(data_root, asset_id, assets_file_row)
            AssetsDef.check_structure(r)
            result += [r]

        else:
            print(f'brakujący typ: {rodzaj_importu}')


    result = pd.concat(result)
    AssetsDef.check_structure(result)
    return result
