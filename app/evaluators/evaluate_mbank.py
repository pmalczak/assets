# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from datetime import date
from pathlib import Path

import pandas as pd

from evaluators.valuation_date import filter_on_or_before, format_date_columns
from importers.assets.data_model import AssetsDef, GroupDomain, TypeDomain
from importers.mbank.data_model import MBankFile
from importers.mbank.read_m_transactions import read_m_transactions


def evaluate_mbank(
    data_root: Path,
    asset_id: str,
    assets_file_row: pd.Series,
    valuation_date: date,
) -> pd.DataFrame:
    assert isinstance(asset_id, str)

    df = read_m_transactions(data_root, asset_id)
    df = filter_on_or_before(df, MBankFile.MBANK_TRANSACTION_DATE, valuation_date)
    if df.empty:
        return pd.DataFrame(columns=list(AssetsDef.expected_columns()))

    last = df[-1:]
    assets_row = None
    for _, _row in last.iterrows():
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
    return format_date_columns(result, AssetsDef.EVALUATION_DATE)


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
    for _, _row in r.iterrows():
        assets_row = AssetsDef.as_assets_row(assets_file_row)
        assets_row[AssetsDef.GROUP] = GroupDomain.DEPOSIT
        assets_row[AssetsDef.EVALUATION_DATE] = master_asset[AssetsDef.EVALUATION_DATE]
        assets_row[AssetsDef.TYPE] = TypeDomain.DEPOSIT
        assets_row[AssetsDef.DESCR] = _row[KOL_LOKATA]
        assets_row[AssetsDef.VALUE] = - _row[MBankFile.MBANK_AMOUNT]
        result += [assets_row]

    return result
