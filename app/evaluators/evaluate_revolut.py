# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"
from pathlib import Path
import pandas as pd

from importers.assets.data_model import AssetsDef, GroupDomain, KindDomain, TypeDomain
from importers.revolut.data_model import RevolutFile
from importers.revolut.read_r_transactions import read_revolut_transactions


def evaluate_revolut(data_root: Path = None, asset_id: str = None, assets_file_row: pd.Series = None):
    p = data_root / asset_id
    if not p.is_dir():
        raise ValueError(p)
    df = read_revolut_transactions(p, asset_id)
    RevolutFile.check_structure(df)
    if df.empty:
        return df
    last =df[-1:]
    for i, row in last.iterrows():
        assets_row1 = AssetsDef.as_assets_row(assets_file_row)
        assets_row1[AssetsDef.EVALUATION_DATE] = row[RevolutFile.DATE]
        assets_row1[AssetsDef.VALUE] = row[RevolutFile.BALANCE]
        break
    data = [assets_row1]

    if assets_file_row[AssetsDef.KIND].startswith(KindDomain.REVOLUT):
        r = _evaluate_deposits(df, assets_file_row)
        if r:
            data += r

    result = pd.DataFrame(data=data)
    AssetsDef.check_structure(result)
    return result


def _evaluate_deposits(df: pd.DataFrame, assets_file_row: pd.Series) -> list:
    cond = df[RevolutFile.DESCRIPTION] == 'Depositing savings'
    df = df[cond]

    result = []
    for i, row in df.iterrows():
        assets_row1 = AssetsDef.as_assets_row(assets_file_row)
        assets_row1[AssetsDef.VALUE] = - row[RevolutFile.AMOUNT]
        assets_row1[AssetsDef.EVALUATION_DATE] = row[RevolutFile.DATE]
        assets_row1[AssetsDef.GROUP] = GroupDomain.DEPOSIT
        assets_row1[AssetsDef.TYPE] = TypeDomain.DEPOSIT
        assets_row1[AssetsDef.DESCR] = 'lokata'
        result += [assets_row1]

    return result
