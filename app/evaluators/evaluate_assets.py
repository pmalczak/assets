# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

import pandas as pd

from fx.data_model import LastFx
from importers.assets.data_model import AssetsDef, KindDomain
from evaluators.evaluate_assets_file import evaluate_assets_file
from evaluators.evaluate_mbank import evaluate_mbank
from evaluators.evaluate_obigacjeskarbowe import evaluate_obligacjeskarbowe
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

        elif rodzaj_importu == 'obligacje_skarbowe_import':
            asset_id: str = assets_file_row[AssetsDef.ID]
            r = evaluate_obligacjeskarbowe(data_root, asset_id, assets_file_row)
            AssetsDef.check_structure(r)
            result += [r]

        elif rodzaj_importu.startswith('assets.'):
            r = evaluate_assets_file(rodzaj_importu, assets_file_row)
            if r is not None:
                AssetsDef.check_structure(r)
                result += [r]

        else:
            print(f'brakujący typ: {rodzaj_importu}')

    result = pd.concat(result)
    AssetsDef.check_structure(result)

    last_fx = get_last_fx(fx_rates)

    result_fx = pd.merge(result, last_fx, on=AssetsDef.CURRENCY)
    assert len(result) == len(result_fx)

    mask = result_fx[AssetsDef.TYPE] == "cash"
    result_fx.loc[mask, AssetsDef.EVALUATION_DATE] = result_fx.loc[mask, AssetsDef.VALUE_DATE]

    result_fx[AssetsDef.VALUE_PLN] = result_fx[AssetsDef.VALUE] * result_fx[LastFx.FX]
    result_fx[AssetsDef.VALUE_PLN] = result_fx[AssetsDef.VALUE_PLN].round().astype('int')

    value_date = pd.to_datetime(result_fx[AssetsDef.VALUE_DATE], format="%Y-%m-%d")
    evaluation_date = pd.to_datetime(result_fx[AssetsDef.EVALUATION_DATE], format="%Y-%m-%d")
    diff = (value_date - evaluation_date).dt.days
    result_fx[AssetsDef.DAYS_AFTER_VALUATION] = diff
    return result_fx
