# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from datetime import date
from pathlib import Path

import pandas as pd

from data_step.data_step import DATA_STEP
from evaluators.valuation_date import filter_on_or_before, format_date_columns
from importers.assets.data_model import AssetsDef, TypeDomain
from importers.pkobp.data_model import PkoBpBonds
from importers.pkobp.import_bonds import import_bonds


def evaluate_obligacjeskarbowe(
    data_root: Path,
    asset_id: str,
    assets_file_row: pd.Series,
    valuation_date: date,
) -> pd.DataFrame:
    assert isinstance(asset_id, str)

    p = data_root / asset_id
    if not p.is_dir():
        raise ValueError(p)

    df = read_obligacje(p, asset_id)
    df = filter_on_or_before(df, PkoBpBonds.DATE, valuation_date)
    if df.empty:
        return pd.DataFrame(columns=list(AssetsDef.expected_columns()))

    data = []
    for _, row in df.iterrows():
        assets_row1 = AssetsDef.as_assets_row(assets_file_row)
        assets_row1[AssetsDef.VALUE] = row[PkoBpBonds.AMOUNT]
        assets_row1[AssetsDef.EVALUATION_DATE] = row[PkoBpBonds.DATE]
        assets_row1[AssetsDef.TYPE] = TypeDomain.BONDS
        assets_row1[AssetsDef.DESCR] = row[PkoBpBonds.CODE]
        data += [assets_row1]

    result = pd.DataFrame(data=data)
    AssetsDef.check_structure(result)
    return format_date_columns(result, AssetsDef.EVALUATION_DATE)


def read_obligacje(input_path: Path, asset_id: str) -> pd.DataFrame:
    resource = f'01 source/{asset_id}.parquet'
    r = DATA_STEP.obtain_dependent(resource, import_bonds, input_path)
    return r.data_frame()
