from __future__ import annotations

import pandas as pd

from analyse_assets.account_tx import (
    AccountTx,
    empty_account_tx,
    mbank_statement_to_account_tx,
    revolut_statement_to_account_tx,
)
from analyse_assets.consolidate_and_drop_internal_transfers import consolidate_account_tx_drop_internal_transfers
from app_proc.data_root import resolve_asset_dir
from importers.assets.data_model import AssetsFile
from importers.assets.pool_id import POOL_ID_COLUMN, POOL_IDS
from importers.assets.read_assets import read_assets
from importers.mbank.read_m_transactions import read_m_transactions
from importers.revolut.read_r_transactions import read_revolut_account_transactions


def load_accounts_pool(pool_id: str) -> pd.DataFrame:
    """Wczytuje i konsoliduje transakcje ROR dla danego pool_id (AccountTx)."""
    if pool_id not in POOL_IDS:
        raise ValueError(f"Nieznany pool_id={pool_id!r}; dozwolone: {POOL_IDS}")

    assets = read_assets()
    assets = assets[assets[POOL_ID_COLUMN].astype(str) == pool_id]
    if assets.empty:
        return empty_account_tx()

    statements: list[pd.DataFrame] = []

    if pool_id.startswith("mbank"):
        for _, asset_row in assets.iterrows():
            asset_id = str(asset_row[AssetsFile.ID])
            asset_dir = resolve_asset_dir(asset_id, asset_row[AssetsFile.TYPE])
            raw = read_m_transactions(asset_dir, asset_id)
            statements.append(
                mbank_statement_to_account_tx(raw, account_id=asset_id, pool_id=pool_id)
            )
        bank = "mbank"
    elif pool_id.startswith("revolut"):
        for _, asset_row in assets.iterrows():
            asset_id = str(asset_row[AssetsFile.ID])
            asset_dir = resolve_asset_dir(asset_id, asset_row[AssetsFile.TYPE])
            raw = read_revolut_account_transactions(asset_dir, asset_id)
            statements.append(
                revolut_statement_to_account_tx(raw, account_id=asset_id, pool_id=pool_id)
            )
        bank = "revolut"
    else:
        raise ValueError(f"Brak obsługi banku dla pool_id={pool_id!r}")

    if not statements:
        return empty_account_tx()

    df, _report, _meta = consolidate_account_tx_drop_internal_transfers(
        statements, bank=bank
    )
    if AccountTx.POOL_ID not in df.columns:
        df[AccountTx.POOL_ID] = pool_id
    else:
        df[AccountTx.POOL_ID] = df[AccountTx.POOL_ID].fillna(pool_id).astype(str)
        df.loc[df[AccountTx.POOL_ID].isin({"", "nan"}), AccountTx.POOL_ID] = pool_id
    return df
