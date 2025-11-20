# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"
from pathlib import Path
import pandas as pd

from evaluators.eveluate_revolut_deposits import evaluate_revolut_deposits
from importers.assets.data_model import AssetsDef, GroupDomain, KindDomain, TypeDomain
from importers.revolut.revolut_account_file import RevolutAccountFile
from importers.revolut.read_r_transactions import read_revolut_account_transactions, read_revolut_deposit_transactions


def evaluate_revolut(data_root: Path = None, asset_id: str = None, assets_file_row: pd.Series = None):
    p = data_root / asset_id
    if not p.is_dir():
        raise ValueError(p)
    df = read_revolut_account_transactions(p, asset_id)
    RevolutAccountFile.check_structure(df)
    if df.empty:
        return df
    last =df[-1:]
    for i, row in last.iterrows():
        assets_row = AssetsDef.as_assets_row(assets_file_row)
        assets_row[AssetsDef.EVALUATION_DATE] = row[RevolutAccountFile.DATE]
        assets_row[AssetsDef.VALUE] = row[RevolutAccountFile.BALANCE]
        break
    data = [assets_row]

    df_dep = read_revolut_deposit_transactions(p, asset_id)
    # RevolutFile.check_structure(df)
    if df_dep.empty:
        return df_dep
    # last =df[-1:]
    last = df_dep[df_dep['Description'] == 'Money carried forward']
    for i, row in last.iterrows():
        assets_row = AssetsDef.as_assets_row(assets_file_row)
        assets_row[AssetsDef.EVALUATION_DATE] = row[RevolutAccountFile.DATE]
        assets_row[AssetsDef.VALUE] = row[RevolutAccountFile.BALANCE]

        assets_row[AssetsDef.GROUP] = GroupDomain.DEPOSIT
        assets_row[AssetsDef.TYPE] = 'depozyt'
        assets_row[AssetsDef.DESCR] = 'deposit'


        break
    data += [assets_row]

    if assets_file_row[AssetsDef.KIND].startswith(KindDomain.REVOLUT):
        r = evaluate_revolut_deposits(df, assets_file_row, product='robo portfolio',
                                      depositing_selector='To Robo portfolio',
                                      withdrowing_selector='From Robo portfolio')
        if r:
            data += r

    result = pd.DataFrame(data=data)
    AssetsDef.check_structure(result)
    return result
