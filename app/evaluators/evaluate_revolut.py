# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from datetime import date
from pathlib import Path

import pandas as pd

from evaluators.valuation_date import filter_on_or_before, format_date_columns
from app_proc.data_root import resolve_asset_dir
from importers.assets.data_model import AssetsDef, GroupDomain, TypeDomain
from importers.revolut.account_data_model import RevolutAccountFile
from importers.revolut.read_r_transactions import read_revolut_account_transactions
from importers.revolut.read_r_deposits import read_revolut_deposit_transactions
from importers.revolut.deposit_data_model import RevolutDepositFile
from roi.revolut_deposit_roi import (
    latest_deposit_balance,
    tax_liability_asset_id,
    tax_liability_value,
)


def evaluate_revolut(
    data_root: Path = None,
    asset_id: str = None,
    assets_file_row: pd.Series = None,
    valuation_date: date = None,
):
    del data_root  # API kompatybilne; katalog z resolve_asset_dir
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
        balance = latest_deposit_balance(df_dep, valuation_date)
        ref_date = df_accounts[RevolutAccountFile.FILE_DATE].unique()[0]
        deposit_row = AssetsDef.as_assets_row(assets_file_row)
        deposit_row[AssetsDef.EVALUATION_DATE] = ref_date
        deposit_row[AssetsDef.VALUE] = balance
        deposit_row[AssetsDef.GROUP] = GroupDomain.DEPOSIT
        deposit_row[AssetsDef.TYPE] = TypeDomain.DEPOSIT
        deposit_row[AssetsDef.DESCR] = "deposit"
        data.append(deposit_row)

        tax_value = tax_liability_value(df_dep, valuation_date)
        if abs(tax_value) > 1e-9:
            tax_row = AssetsDef.as_assets_row(assets_file_row)
            tax_row[AssetsDef.ID] = tax_liability_asset_id(asset_id, valuation_date.year)
            tax_row[AssetsDef.EVALUATION_DATE] = ref_date
            tax_row[AssetsDef.VALUE] = tax_value
            tax_row[AssetsDef.GROUP] = GroupDomain.DEPOSIT
            tax_row[AssetsDef.TYPE] = TypeDomain.DEPOSIT
            tax_row[AssetsDef.DESCR] = "zobowiazanie_podatkowe"
            data.append(tax_row)

    # Robo / rachunek brokerski: pozycje z trading-* (RODZAJ*=BROKER), nie FIFO przelewów ROR.

    result = pd.DataFrame(data=data)
    AssetsDef.check_structure(result)
    return format_date_columns(result, AssetsDef.EVALUATION_DATE)
