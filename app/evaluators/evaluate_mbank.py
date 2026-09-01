# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from datetime import date
from pathlib import Path

import pandas as pd

from evaluators.valuation_date import filter_on_or_before, format_date_columns
from app_proc.data_root import resolve_asset_dir
from importers.assets.data_model import AssetsDef, GroupDomain, TypeDomain
from importers.mbank.data_model import MBankFile
from importers.mbank.read_m_transactions import read_m_transactions
from roi.mbank_deposit_roi import build_mbank_lokata_cashflows, compute_lokata_roi


def evaluate_mbank(
    data_root: Path,
    asset_id: str,
    assets_file_row: pd.Series,
    valuation_date: date,
) -> pd.DataFrame:
    assert isinstance(asset_id, str)

    asset_dir = resolve_asset_dir(asset_id, assets_file_row[AssetsDef.TYPE])
    df = read_m_transactions(asset_dir, asset_id)
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
        r = _evaluate_deposits_mbank(
            df, assets_file_row, assets_row, asset_id, valuation_date
        )
        if r:
            data += r

    result = pd.DataFrame(data=data)
    AssetsDef.check_structure(result)
    return format_date_columns(result, AssetsDef.EVALUATION_DATE)


def _evaluate_deposits_mbank(
    df: pd.DataFrame,
    assets_file_row: pd.Series,
    master_asset: pd.Series,
    account_id: str,
    valuation_date: date,
) -> list:
    events, _warnings = build_mbank_lokata_cashflows(df, account_id)
    total = 0.0
    n_open = 0
    for asset_id, cashflows in events.items():
        summary = compute_lokata_roi(asset_id, cashflows, valuation_date)
        if summary.is_sold:
            continue
        total += float(summary.terminal_unrealized)
        n_open += 1
    if n_open == 0 or abs(total) < 1e-9:
        return []

    assets_row = AssetsDef.as_assets_row(assets_file_row)
    assets_row[AssetsDef.GROUP] = GroupDomain.DEPOSIT
    assets_row[AssetsDef.EVALUATION_DATE] = master_asset[AssetsDef.EVALUATION_DATE]
    assets_row[AssetsDef.TYPE] = TypeDomain.DEPOSIT
    assets_row[AssetsDef.DESCR] = _deposit_descr(n_open)
    assets_row[AssetsDef.VALUE] = total
    return [assets_row]


def _deposit_descr(n_open: int) -> str:
    if n_open == 1:
        return "depozyty (1 lokata)"
    if 2 <= n_open <= 4:
        return f"depozyty ({n_open} lokaty)"
    return f"depozyty ({n_open} lokat)"
