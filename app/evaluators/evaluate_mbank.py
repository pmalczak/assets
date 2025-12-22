# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from data_step.data_step import DATA_STEP
from importers.assets.data_model import AssetsDef, GroupDomain
from importers.mbank.data_model import MBankFile
from importers.mbank.read_m_transactions import read_m_transactions


def evaluate_mbank(data_root, asset_id: str, assets_file_row: pd.Series) -> pd.DataFrame:
    assert isinstance(asset_id, str)
    r = DATA_STEP.obtain(f'02 evaluated/{asset_id}.parquet', _evaluate_mbank,
                         data_root=data_root, asset_id=asset_id, assets_file_row=assets_file_row)
    return r.data_frame()


def _evaluate_mbank(data_root: Path = None,
                    asset_id: str = None, assets_file_row : pd.Series = None):

    df = read_m_transactions(data_root, asset_id)
    last =df[-1:]
    for i, _row in last.iterrows():
        assets_row = AssetsDef.as_assets_row(assets_file_row)
        assets_row[AssetsDef.IBAN] = _row[MBankFile.DEBIT_ACCOUNT]
        assets_row[AssetsDef.VALUE] = _row[MBankFile.MBANK_OUTSTANDING_BALANCE]
        assets_row[AssetsDef.EVALUATION_DATE] = _row[MBankFile.FILE_DATE]
        break
    data = [assets_row]

    if assets_file_row[AssetsDef.KIND].startswith('mbank.'):
        r = _evaluate_deposits_mbank(df, assets_file_row, assets_row)
        if r:
            data += r

    result = pd.DataFrame(data=data)
    AssetsDef.check_structure(result)

    return result


def _evaluate_deposits_mbank(df: pd.DataFrame, assets_file_row: pd.Series, master_asset: pd.Series) -> list:
    KOL_LOKATA = 'lokata'

    pattern = r"(NR \d{15})"
    df[KOL_LOKATA] = df[MBankFile.MBANK_TITLE].str.extract(pattern, expand=False)

    r = df[df[KOL_LOKATA].notnull()]

    active_deposits = r[[KOL_LOKATA, MBankFile.MBANK_AMOUNT]]
    active_deposits = active_deposits.groupby(KOL_LOKATA).sum()
    active_deposits = active_deposits[active_deposits[MBankFile.MBANK_AMOUNT] < 0.0]
    active_deposits = active_deposits.reset_index()
    active_deposits = active_deposits[[KOL_LOKATA]]

    r = r.merge(active_deposits, on=KOL_LOKATA)

    result = []
    for i, _row in r.iterrows():
        assets_row = AssetsDef.as_assets_row(assets_file_row)
        assets_row[AssetsDef.GROUP] = GroupDomain.DEPOSIT
        assets_row[AssetsDef.EVALUATION_DATE] = master_asset[AssetsDef.EVALUATION_DATE]
        assets_row[AssetsDef.TYPE] = 'depozyt'
        assets_row[AssetsDef.DESCR] = _row[KOL_LOKATA]
        assets_row[AssetsDef.VALUE] = - _row[MBankFile.MBANK_AMOUNT]
        result += [assets_row]

    return result
