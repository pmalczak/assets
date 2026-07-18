from __future__ import annotations

import pandas as pd

from analyse_assets.consolidate_and_drop_internal_transfers import consolidate_many_drop_internal_transfers
from analyse_assets.config_model import DEFAULT_TRANSACTION_SOURCE, MBANK_EUR_TRANSACTION_SOURCE
from analyse_assets.config_model import AnalyseAssetsCatalog, MBANK_SOURCE_ACCOUNT_COLUMN
from app_proc.data_root import get_online_data_root
from importers.assets.data_model import AssetsFile, KindDomain
from importers.assets.read_assets import read_assets
from importers.mbank.read_m_transactions import read_m_transactions


MBANK_PLN = 'mbank_pln'
MBANK_EUR = 'mbank_eur'
REVOLUT_PLN = 'revolut_pln'
REVOLUT_EUR = 'revolut_eur'

POOL_IDS = (MBANK_EUR, MBANK_PLN, REVOLUT_EUR, REVOLUT_PLN)


def load_mbank_pool() -> pd.DataFrame:
    assets = read_assets()
    assets = assets[assets[AssetsFile.KIND].str.startswith(KindDomain.MBANK)]
    assets = assets[assets[AssetsFile.CURRENCY].isin(["PLN", "EUR"])]

    data_root = get_online_data_root()
    statements = []
    for _, asset_row in assets.iterrows():
        asset_id = str(asset_row[AssetsFile.ID])
        source = _mbank_source_for_currency(asset_row[AssetsFile.CURRENCY])
        df = read_m_transactions(data_root, asset_id)
        df[MBANK_SOURCE_ACCOUNT_COLUMN] = asset_id
        df[AnalyseAssetsCatalog.SOURCE] = source
        statements.append(df)

    if not statements:
        return pd.DataFrame()

    df, _report, _meta = consolidate_many_drop_internal_transfers(statements)
    if AnalyseAssetsCatalog.SOURCE not in df.columns:
        df[AnalyseAssetsCatalog.SOURCE] = DEFAULT_TRANSACTION_SOURCE
    return df


def _mbank_source_for_currency(currency: str) -> str:
    code = str(currency).strip().upper()
    if code == "EUR":
        return MBANK_EUR_TRANSACTION_SOURCE
    if code == "PLN":
        return DEFAULT_TRANSACTION_SOURCE
    raise ValueError(f"Nieobsługiwana waluta konta mBank w poolu ROI: {currency!r}")
