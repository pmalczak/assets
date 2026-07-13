# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

import pandas as pd

from data_step.data_step import DATA_STEP
from data_step.data_strep_data_types import REFRESHED
from app_proc.data_steps_root import get_data_steps_root
from roi.allocate import allocate_catalog
from roi.compute_roi import load_mbank_pool
from roi.config import get_config_file, read_analyse_config
from roi.data_model import CashFlowEvent

ROI_EVENTS_STEP = "10 roi_events"
ROI_CATALOG_RESOURCE = f"{ROI_EVENTS_STEP}/_catalog.parquet"
ROI_UNALLOCATED_RESOURCE = f"{ROI_EVENTS_STEP}/_unallocated.parquet"


def roi_events_resource(asset_id: str) -> str:
    return f"{ROI_EVENTS_STEP}/{asset_id}.parquet"


def load_catalog_events(
    config: dict[str, pd.DataFrame] | None = None,
    *,
    config_path: Path | None = None,
    use_cache: bool = True,
) -> dict[str, pd.DataFrame]:
    if config is None:
        config = read_analyse_config(config_path)

    if not use_cache:
        events_by_asset, _unallocated = _build_allocation(config)
        return events_by_asset

    DATA_STEP.init_steps(root=get_data_steps_root())
    config_file = get_config_file(config_path)
    r = DATA_STEP.obtain_dependent(
        ROI_CATALOG_RESOURCE,
        _build_all_events,
        config_file,
    )
    all_events = r.data_frame()
    return _split_by_asset(all_events, config["catalog"])


def load_unallocated_mbank(
    config: dict[str, pd.DataFrame] | None = None,
    *,
    config_path: Path | None = None,
    use_cache: bool = True,
) -> pd.DataFrame:
    if config is None:
        config = read_analyse_config(config_path)

    if not use_cache:
        _events_by_asset, unallocated = _build_allocation(config)
        return unallocated

    _ensure_unallocated_cache(config_path)
    load_catalog_events(config, config_path=config_path, use_cache=True)
    DATA_STEP.init_steps(root=get_data_steps_root())
    path = DATA_STEP.get_absolute_file_path(ROI_UNALLOCATED_RESOURCE)
    if not path.is_file():
        _events_by_asset, unallocated = _build_allocation(config)
        _save_unallocated_side_product(unallocated)
        return unallocated
    return DATA_STEP.read_featured_file(path)


def _ensure_unallocated_cache(config_path: Path | None = None) -> None:
    """Wymusza przebudowe ROI, gdy catalog jest w cache bez pliku unallocated."""
    DATA_STEP.init_steps(root=get_data_steps_root())
    unallocated_path = DATA_STEP.get_absolute_file_path(ROI_UNALLOCATED_RESOURCE)
    if unallocated_path.is_file():
        return

    metadata = DATA_STEP.metadata.get_metadata()
    if ROI_CATALOG_RESOURCE not in metadata:
        return

    DATA_STEP.metadata.delete(ROI_CATALOG_RESOURCE)
    if ROI_UNALLOCATED_RESOURCE in metadata:
        DATA_STEP.metadata.delete(ROI_UNALLOCATED_RESOURCE)
    DATA_STEP.metadata.dump_metadata()


def _build_allocation(
    config: dict[str, pd.DataFrame],
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    catalog = config["catalog"]
    catalog = catalog[catalog["enabled"].astype(bool)].sort_values("order")
    pool = load_mbank_pool()
    return allocate_catalog(pool, catalog, config["rules"], config["manual"])


def _build_all_events(source_file: Path | None = None) -> pd.DataFrame:
    config = read_analyse_config(source_file)
    events_by_asset, unallocated = _build_allocation(config)
    _save_unallocated_side_product(unallocated)

    frames = [events for events in events_by_asset.values() if not events.empty]
    if not frames:
        return pd.DataFrame(columns=list(CashFlowEvent.COLUMN_ORDER))
    result = pd.concat(frames, ignore_index=True)
    CashFlowEvent.check_structure(result)
    return result


def _save_unallocated_side_product(unallocated: pd.DataFrame) -> None:
    DATA_STEP._dependencies.create(ROI_UNALLOCATED_RESOURCE)
    for dependency in DATA_STEP._dependencies.get(ROI_CATALOG_RESOURCE):
        DATA_STEP._dependencies.update(ROI_UNALLOCATED_RESOURCE, dependency)
    DATA_STEP.save(REFRESHED, ROI_UNALLOCATED_RESOURCE, unallocated)


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
