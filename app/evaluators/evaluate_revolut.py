# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from datetime import date
from pathlib import Path

import pandas as pd

from evaluators.eveluate_revolut_deposits import evaluate_revolut_deposits
from evaluators.valuation_date import filter_on_or_before, format_date_columns
from app_proc.data_root import resolve_asset_dir
from importers.assets.data_model import AssetsDef, GroupDomain, KindDomain, TypeDomain
from importers.revolut.account_data_model import RevolutAccountFile
from importers.revolut.read_r_transactions import read_revolut_account_transactions
from importers.revolut.read_r_deposits import read_revolut_deposit_transactions
from importers.revolut.deposit_data_model import RevolutDepositFile


def evaluate_revolut(
    data_root: Path = None,
    asset_id: str = None,
    assets_file_row: pd.Series = None,
    valuation_date: date = None,
):
    p = resolve_asset_dir(asset_id, assets_file_row[AssetsDef.TYPE])
    if not p.is_dir():
        raise ValueError(p)

    df_accounts = read_revolut_account_transactions(p, asset_id)
    RevolutAccountFile.check_structure(df_accounts)
    df_accounts = filter_on_or_before(df_accounts, RevolutAccountFile.DATE, valuation_date)
    if df_accounts.empty:
        return df_accounts

    last = df_accounts[-1:]
    assets_row = None
    for _, row in last.iterrows():
        assets_row = AssetsDef.as_assets_row(assets_file_row)
        assets_row[AssetsDef.EVALUATION_DATE] = row[RevolutAccountFile.FILE_DATE]
        assets_row[AssetsDef.VALUE] = row[RevolutAccountFile.BALANCE]
        break
    data = [assets_row]

    df_dep = read_revolut_deposit_transactions(p, asset_id)
    df_dep = filter_on_or_before(df_dep, RevolutDepositFile.DATE, valuation_date)
    if not df_dep.empty:
        last = df_dep[df_dep[RevolutDepositFile.DESCRIPTION] == 'Money carried forward']
        if not last.empty:
            last = last[-1:]
            ref_date = df_accounts[RevolutAccountFile.FILE_DATE].unique()[0]
            for _, row in last.iterrows():
                deposit_row = AssetsDef.as_assets_row(assets_file_row)
                deposit_row[AssetsDef.EVALUATION_DATE] = ref_date
                deposit_row[AssetsDef.VALUE] = row[RevolutAccountFile.BALANCE]
                deposit_row[AssetsDef.GROUP] = GroupDomain.DEPOSIT
                deposit_row[AssetsDef.TYPE] = TypeDomain.DEPOSIT
                deposit_row[AssetsDef.DESCR] = 'deposit'
                data += [deposit_row]
                break

    if assets_file_row[AssetsDef.KIND].startswith(KindDomain.REVOLUT):
        r = evaluate_revolut_deposits(
            df_accounts,
            assets_file_row,
            product='robo portfolio',
            depositing_selector='To Robo portfolio',
            withdrowing_selector='From Robo portfolio',
        )
        if r:
            data += r

    result = pd.DataFrame(data=data)
    AssetsDef.check_structure(result)
    return format_date_columns(result, AssetsDef.EVALUATION_DATE)
