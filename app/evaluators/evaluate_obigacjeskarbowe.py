# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from data_step.data_step import DATA_STEP
from assets.data_model import AssetsDef
from importers.pkobp.data_model import PkoBpBonds
from importers.pkobp.import_bonds import import_bonds


def evaluate_obligacjeskarbowe(data_root, asset_id: str, assets_file_row: pd.Series) -> pd.DataFrame:
    assert isinstance(asset_id, str)
    r = DATA_STEP.obtain(f'02 evaluated/{asset_id}.parquet', _evaluate_obligacjeskarbowe,
                         data_root=data_root, asset_id=asset_id, assets_file_row=assets_file_row)
    result = r.data_frame()
    return result


def _evaluate_obligacjeskarbowe(data_root: Path = None, asset_id: str = None, assets_file_row: pd.Series = None):
    p = data_root / asset_id
    if not p.is_dir():
        raise ValueError(p)
    df = read_obligacje(p, asset_id)

    data = []
    for i, row in df.iterrows():
        assets_row1 = AssetsDef.as_assets_row(assets_file_row)
        assets_row1[AssetsDef.VALUE] = row[PkoBpBonds.AMOUNT]
        assets_row1[AssetsDef.EVALUATION_DATE] = row[PkoBpBonds.DATE]
        assets_row1[AssetsDef.TYPE] = 'obligacje'
        assets_row1[AssetsDef.DESCR] = row[PkoBpBonds.CODE]
        data += [assets_row1]

    result = pd.DataFrame(data=data)
    AssetsDef.check_structure(result)
    return result


def read_obligacje(input_path: Path, asset_id: str) -> pd.DataFrame:
    resource = f'01 source/{asset_id}.parquet'
    r = DATA_STEP.obtain(resource, import_bonds, input_path=input_path)
    result = r.data_frame()
    return result
