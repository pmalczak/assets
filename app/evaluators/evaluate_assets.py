# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

import pandas as pd

from fx.data_model import LastFx
from importers.assets.data_model import AssetsDef, KindDomain
from evaluators.evaluate_assets_file import evaluate_assets_file_content
from evaluators.evaluate_mbank import evaluate_mbank
from evaluators.evaluate_obigacjeskarbowe import evaluate_obligacjeskarbowe
from evaluators.evaluate_regnology import evaluate_regnology
from evaluators.evaluate_revolut import evaluate_revolut
from fx.get_last_fx import get_last_fx


def evaluate_assets(data_root, assets: pd.DataFrame, fx_rates: pd.DataFrame) -> pd.DataFrame:

    result = []
    a = assets[assets[AssetsDef.KIND].notnull()]
    for i, assets_file_row in a.iterrows():
        assert isinstance(assets_file_row, pd.Series)
        rodzaj_importu: str = assets_file_row[AssetsDef.KIND]

        if rodzaj_importu.startswith(KindDomain.MBANK):
            asset_id: str = assets_file_row[AssetsDef.ID]
            r = evaluate_mbank(data_root, asset_id, assets_file_row)
            AssetsDef.check_structure(r)
            result += [r]

        elif rodzaj_importu.startswith(KindDomain.REVOLUT):
            asset_id: str = assets_file_row[AssetsDef.ID]
            r = evaluate_revolut(data_root, asset_id, assets_file_row)
            if len(r) > 0:
                AssetsDef.check_structure(r)
                result += [r]

        elif rodzaj_importu == KindDomain.REGNOLOGY:
            asset_id: str = assets_file_row[AssetsDef.ID]
            r = evaluate_regnology(data_root, asset_id, assets_file_row)
            AssetsDef.check_structure(r)
            result += [r]

        elif rodzaj_importu == 'obligacje_skarbowe_import':
            asset_id: str = assets_file_row[AssetsDef.ID]
            r = evaluate_obligacjeskarbowe(data_root, asset_id, assets_file_row)
            AssetsDef.check_structure(r)
            result += [r]

        elif rodzaj_importu.startswith('assets.IKE-'):
            # asset_id: str = assets_file_row[AssetsDef.ID]
            r = evaluate_assets_file_content(assets_file_row)
            AssetsDef.check_structure(r)
            result += [r]

        else:
            print(f'brakujący typ: {rodzaj_importu}')

    result = pd.concat(result)
    AssetsDef.check_structure(result)

    last_fx = get_last_fx(fx_rates)

    result1 = pd.merge(result, last_fx, on=AssetsDef.CURRENCY)
    assert len(result) == len(result1)
    result1[AssetsDef.VALUE_PLN] = result1[AssetsDef.VALUE] * result1[LastFx.FX]
    result1[AssetsDef.VALUE_PLN] = result1[AssetsDef.VALUE_PLN].round().astype('int')
    return result1
