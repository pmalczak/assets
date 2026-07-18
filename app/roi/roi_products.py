# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from analyse_assets.account_tx import AccountTx, add_ymd_columns, empty_account_tx
from analyse_assets.accounts_pools import load_accounts_pool
from analyse_assets.config_model import AnalyseAssetsCatalog, DEFAULT_POOL_ID
from analyse_assets.build_selector import is_blank_rule_value
from data_step.data_step import DATA_STEP
from importers.assets.pool_id import POOL_IDS
from roi.allocate import allocate_catalog
from roi.config import get_config_file, read_analyse_config
from roi.data_model import CashFlowEvent

ROI_STEP = "10 roi"


def roi_catalog_resource(assets_date: date) -> str:
    return f"{ROI_STEP}/{assets_date:%Y-%m-%d}/_catalog.parquet"


def roi_unallocated_resource(assets_date: date, pool_id: str) -> str:
    return f"{ROI_STEP}/{assets_date:%Y-%m-%d}/_unallocated_{pool_id}.parquet"


def add_account_tx_ymd_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Dodaje kolumny ROK/MIESIAC/DZIEN na podstawie transaction_date."""
    return add_ymd_columns(df.copy())


# Alias kompatybilności
add_mbank_consolidated_ymd_columns = add_account_tx_ymd_columns


def load_catalog_events(
    assets_date: date,
    config: dict[str, pd.DataFrame] | None = None,
    *,
    config_path: Path | None = None,
) -> dict[str, pd.DataFrame]:
    if config is None:
        config = read_analyse_config(config_path)

    config_file = get_config_file(config_path)
    r = DATA_STEP.obtain_dependent(
        roi_catalog_resource(assets_date),
        _build_catalog_events,
        config_file,
        assets_date=assets_date,
    )
    return _split_by_asset(r.data_frame(), config["catalog"])


def load_unallocated_pool(
    assets_date: date,
    pool_id: str | None = None,
    config: dict[str, pd.DataFrame] | None = None,
    *,
    config_path: Path | None = None,
) -> pd.DataFrame:
    """
    Niezaalokowane transakcje.
    z pool_id: jeden DF; bez: concat wszystkich znanych produktów dla daty.
    """
    if config is None:
        config = read_analyse_config(config_path)

    # Catalog rebuild materializuje unallocated per pool_id.
    load_catalog_events(assets_date, config, config_path=config_path)

    if pool_id is not None:
        if pool_id not in POOL_IDS:
            raise ValueError(f"Nieznany pool_id={pool_id!r}")
        pool_ids = [pool_id]
    else:
        pool_ids = _enabled_pool_ids(config["catalog"])

    config_file = get_config_file(config_path)
    frames: list[pd.DataFrame] = []
    for pid in pool_ids:
        r = DATA_STEP.obtain_dependent(
            roi_unallocated_resource(assets_date, pid),
            _build_unallocated_for_pool,
            config_file,
            assets_date=assets_date,
            pool_id=pid,
        )
        frames.append(add_account_tx_ymd_columns(r.data_frame()))

    if not frames:
        return empty_account_tx()
    if len(frames) == 1:
        return frames[0]
    return pd.concat(frames, ignore_index=True)


def load_unallocated_mbank(
    assets_date: date,
    config: dict[str, pd.DataFrame] | None = None,
    *,
    config_path: Path | None = None,
) -> pd.DataFrame:
    """Deprecated alias: wszystkie niezaalokowane pool'e."""
    return load_unallocated_pool(assets_date, pool_id=None, config=config, config_path=config_path)


def _enabled_pool_ids(catalog: pd.DataFrame) -> list[str]:
    enabled = catalog[catalog["enabled"].astype(bool)]
    if enabled.empty or AnalyseAssetsCatalog.POOL_ID not in enabled.columns:
        return [DEFAULT_POOL_ID]
    ordered: list[str] = []
    for value in enabled.sort_values("order")[AnalyseAssetsCatalog.POOL_ID].tolist():
        if is_blank_rule_value(value):
            pid = DEFAULT_POOL_ID
        else:
            pid = str(value).strip()
        if pid not in ordered:
            ordered.append(pid)
    return ordered or [DEFAULT_POOL_ID]


def _build_allocation(
    config: dict[str, pd.DataFrame],
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    catalog = config["catalog"]
    enabled = catalog[catalog["enabled"].astype(bool)].sort_values("order")
    rules = config["rules"]
    manual = config["manual"]

    events_by_asset: dict[str, pd.DataFrame] = {}
    unallocated_by_pool: dict[str, pd.DataFrame] = {}

    for pool_id in _enabled_pool_ids(catalog):
        pool = load_accounts_pool(pool_id)
        sub_catalog = enabled[
            enabled[AnalyseAssetsCatalog.POOL_ID].astype(str).str.strip() == pool_id
        ]
        if sub_catalog.empty:
            unallocated_by_pool[pool_id] = add_account_tx_ymd_columns(pool)
            continue
        events, unallocated = allocate_catalog(pool, sub_catalog, rules, manual)
        events_by_asset.update(events)
        unallocated_by_pool[pool_id] = add_account_tx_ymd_columns(unallocated)

    return events_by_asset, unallocated_by_pool


def _build_catalog_events(
    source_file: Path | None = None,
    *,
    assets_date: date,
    **_kwargs,
) -> pd.DataFrame:
    config = read_analyse_config(source_file)
    events_by_asset, unallocated_by_pool = _build_allocation(config)

    for pool_id, unallocated in unallocated_by_pool.items():

        def _materialize(unalloc=unallocated, **_kw) -> pd.DataFrame:
            return unalloc

        DATA_STEP.obtain(
            roi_unallocated_resource(assets_date, pool_id),
            _materialize,
        )

    all_unallocated = (
        pd.concat(list(unallocated_by_pool.values()), ignore_index=True)
        if unallocated_by_pool
        else empty_account_tx()
    )
    _export_roi_mbank_excels(events_by_asset, all_unallocated, config["catalog"], assets_date)

    frames = [events for events in events_by_asset.values() if not events.empty]
    if not frames:
        return pd.DataFrame(columns=list(CashFlowEvent.COLUMN_ORDER))
    result = pd.concat(frames, ignore_index=True)
    result[CashFlowEvent.DATE] = (
        pd.to_datetime(result[CashFlowEvent.DATE], errors="coerce").dt.strftime("%Y-%m-%d")
    )
    result = result.dropna(subset=[CashFlowEvent.DATE]).reset_index(drop=True)
    CashFlowEvent.check_structure(result)
    return result


def _build_unallocated_for_pool(
    source_file: Path | None = None,
    *,
    assets_date: date,
    pool_id: str,
    **_kwargs,
) -> pd.DataFrame:
    config = read_analyse_config(source_file)
    _events_by_asset, unallocated_by_pool = _build_allocation(config)
    return add_account_tx_ymd_columns(
        unallocated_by_pool.get(pool_id, empty_account_tx())
    )


def _export_roi_mbank_excels(
    events_by_asset: dict[str, pd.DataFrame],
    unallocated: pd.DataFrame,
    catalog: pd.DataFrame,
    assets_date: date,
) -> None:
    from app_proc.export_product_excel import export_roi_mbank_excels

    export_roi_mbank_excels(
        events_by_asset,
        add_account_tx_ymd_columns(unallocated),
        catalog,
        assets_date,
    )


def _split_by_asset(all_events: pd.DataFrame, catalog: pd.DataFrame) -> dict[str, pd.DataFrame]:
    enabled = catalog[catalog["enabled"].astype(bool)].sort_values("order")
    result: dict[str, pd.DataFrame] = {}
    for _, asset_row in enabled.iterrows():
        asset_id = str(asset_row["asset_id"])
        if all_events.empty:
            result[asset_id] = pd.DataFrame(columns=list(CashFlowEvent.COLUMN_ORDER))
        else:
            result[asset_id] = all_events[all_events[CashFlowEvent.ASSET_ID] == asset_id].copy()
    return result
