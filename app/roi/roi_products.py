# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from analyse_assets.account_tx import AccountTx, add_ymd_columns, empty_account_tx
from analyse_assets.accounts_pools import load_accounts_pool
from analyse_assets.config_model import (
    AnalyseAssetsCatalog,
    AnalyseAssetsRules,
    DEFAULT_POOL_ID,
)
from analyse_assets.build_selector import is_blank_rule_value
from app_proc.data_root import get_online_data_output
from app_proc.export_product_excel import (
    export_roi_product_excels,
    export_roi_summary_excel,
    unallocated_excel_filename,
)
from data_step.data_step import DATA_STEP
from importers.assets.pool_id import POOL_IDS
from roi.allocate import allocate_catalog, collect_pool_ids_from_rules
from roi.config import get_config_file, read_analyse_config
from roi.data_model import CashFlowEvent

ROI_STEP = "10 roi"


def roi_catalog_resource(assets_date: date) -> str:
    return f"{ROI_STEP}/{assets_date:%Y-%m-%d}/_catalog.parquet"


def roi_summary_resource(assets_date: date) -> str:
    return f"{ROI_STEP}/{assets_date:%Y-%m-%d}/_roi_summary.parquet"


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


def load_roi_summary(
    assets_date: date,
    config: dict[str, pd.DataFrame] | None = None,
    *,
    config_path: Path | None = None,
) -> pd.DataFrame:
    """Summary ROI z DATA_STEP (XIRR liczone przy rebuildzie)."""
    if config is None:
        config = read_analyse_config(config_path)

    config_file = get_config_file(config_path)
    r = DATA_STEP.obtain_dependent(
        roi_summary_resource(assets_date),
        _build_roi_summary,
        config_file,
        assets_date=assets_date,
    )
    return r.data_frame()


def load_unallocated_pool(
    assets_date: date,
    pool_id: str | None = None,
    config: dict[str, pd.DataFrame] | None = None,
    *,
    config_path: Path | None = None,
) -> pd.DataFrame:
    """
    Niezaalokowane transakcje z Excel w product/{date}/.
    Wymusza rebuild katalogu (eksport Excel), potem czyta pliki.
    z pool_id: jeden DF; bez: concat wszystkich znanych produktów dla daty.
    """
    if config is None:
        config = read_analyse_config(config_path)

    load_catalog_events(assets_date, config, config_path=config_path)

    if pool_id is not None:
        if pool_id not in POOL_IDS:
            raise ValueError(f"Nieznany pool_id={pool_id!r}")
        pool_ids = [pool_id]
    else:
        pool_ids = _allocation_pool_ids(config["catalog"], config["rules"])

    out_dir = get_online_data_output(assets_date)
    frames: list[pd.DataFrame] = []
    for pid in pool_ids:
        path = out_dir / unallocated_excel_filename(pid)
        if not path.is_file():
            continue
        frames.append(add_account_tx_ymd_columns(pd.read_excel(path)))

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
    """Pool'e z katalogu (assets.pool_id) — bez reguł."""
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


def _allocation_pool_ids(catalog: pd.DataFrame, rules: pd.DataFrame) -> list[str]:
    """Unia assets.pool_id + pooli z rules (kolumna pool_id lub field=POOL_ID equals)."""
    ordered = list(_enabled_pool_ids(catalog))
    enabled = catalog[catalog["enabled"].astype(bool)]
    if enabled.empty:
        return ordered

    enabled_ids = set(enabled[AnalyseAssetsCatalog.ASSET_ID].astype(str).str.strip())
    for pid in collect_pool_ids_from_rules(rules, enabled_ids):
        if pid not in ordered:
            ordered.append(pid)
    return ordered or [DEFAULT_POOL_ID]


def _split_unallocated_by_pool(
    unallocated: pd.DataFrame,
    pool_ids: list[str],
) -> dict[str, pd.DataFrame]:
    """Podziel remaining po AccountTx.POOL_ID; brakujące pool'e → pusta ramka."""
    result: dict[str, pd.DataFrame] = {}
    frame = add_account_tx_ymd_columns(unallocated)
    col = AccountTx.POOL_ID
    for pool_id in pool_ids:
        if frame.empty or col not in frame.columns:
            result[pool_id] = frame.iloc[0:0].copy() if not frame.empty else empty_account_tx()
            continue
        mask = frame[col].astype("string").fillna("") == pool_id
        part = frame.loc[mask].copy()
        result[pool_id] = part if not part.empty else empty_account_tx()
    return result


def _build_allocation(
    config: dict[str, pd.DataFrame],
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    catalog = config["catalog"]
    enabled = catalog[catalog["enabled"].astype(bool)].sort_values("order")
    rules = config["rules"]
    manual = config["manual"]

    pool_ids = _allocation_pool_ids(catalog, rules)
    frames = [load_accounts_pool(pool_id) for pool_id in pool_ids]
    if frames:
        combined = pd.concat(frames, ignore_index=True)
    else:
        combined = empty_account_tx()

    if enabled.empty:
        return {}, _split_unallocated_by_pool(combined, pool_ids)

    events_by_asset, unallocated = allocate_catalog(combined, enabled, rules, manual)
    unallocated_by_pool = _split_unallocated_by_pool(unallocated, pool_ids)
    return events_by_asset, unallocated_by_pool


def _build_catalog_events(
    source_file: Path | None = None,
    *,
    assets_date: date,
    **_kwargs,
) -> pd.DataFrame:
    config = read_analyse_config(source_file)
    events_by_asset, unallocated_by_pool = _build_allocation(config)

    export_roi_product_excels(
        events_by_asset,
        unallocated_by_pool,
        config["catalog"],
        assets_date,
    )

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


def _build_roi_summary(
    source_file: Path | None = None,
    *,
    assets_date: date,
    **_kwargs,
) -> pd.DataFrame:
    from importers.assets.property_lifecycle import catalog_properties_id
    from importers.assets.read_assets import read_property_valuations
    from roi.compute_roi import compute_roi, roi_summary_to_row

    config = read_analyse_config(source_file)
    catalog = config["catalog"]
    catalog = catalog[catalog["enabled"].astype(bool)].sort_values("order")

    events_by_asset = load_catalog_events(assets_date, config, config_path=source_file)
    properties_sheet = read_property_valuations()

    summaries = []
    for _, asset_row in catalog.iterrows():
        asset_id = str(asset_row["asset_id"])
        properties_id = catalog_properties_id(asset_row)
        events = events_by_asset.get(
            asset_id, pd.DataFrame(columns=list(CashFlowEvent.COLUMN_ORDER))
        )
        summary = compute_roi(
            asset_id,
            events,
            properties_sheet,
            assets_date,
            properties_id=properties_id,
        )
        summaries.append(roi_summary_to_row(summary))

    result = pd.DataFrame(summaries)
    export_roi_summary_excel(result, assets_date)
    return result


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
