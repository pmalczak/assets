# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd
from assets.data_model import AssetsDef


def evaluate_regnology(data_root: Path = None, asset_id: str = None, assets_file_row: pd.Series = None) -> pd.DataFrame:
    p = data_root / asset_id
    if not p.is_dir():
        raise ValueError(p)
    df = read_regnolgy_transactions(p)
    last =df[-1:]
    for i, row in last.iterrows():
        assets_row1 = AssetsDef.as_assets_row(assets_file_row)
        assets_row1[AssetsDef.VALUE] = row['wartość']
        assets_row1[AssetsDef.EVALUATION_DATE] = row['Data']
        break
    data = [assets_row1]
    result = pd.DataFrame(data=data)
    AssetsDef.check_structure(result)
    return result


def read_regnolgy_transactions(input_path: Path) -> pd.DataFrame:
    f = input_path / 'rocky-iv.csv'
    result = pd.read_csv(f)
    # RegnologyFile
    return result
