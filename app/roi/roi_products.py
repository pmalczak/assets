# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from analyse_assets.data_model import AssetRw
from data_step.data_step import DATA_STEP
from roi.allocate import allocate_catalog
from roi.compute_roi import load_mbank_pool
from roi.config import get_config_file, read_analyse_config
from roi.data_model import CashFlowEvent

_APP_ROOT = Path(__file__).resolve().parent.parent

ROI_STEP = "10 roi"


def roi_catalog_resource(assets_date: date) -> str:
    return f"{ROI_STEP}/{assets_date:%Y-%m-%d}/_catalog.parquet"


def roi_unallocated_resource(assets_date: date) -> str:
    return f"{ROI_STEP}/{assets_date:%Y-%m-%d}/_unallocated.parquet"


def _ensure_data_step() -> None:
    DATA_STEP.init_steps(root=_APP_ROOT)


def add_mbank_consolidated_ymd_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Dodaje kolumny ROK/MIESIAC/DZIEN (AssetRw) na podstawie daty operacji mBank."""
    return AssetRw.add_ymd_columns(df.copy())


def load_catalog_events(
    assets_date: date,
    config: dict[str, pd.DataFrame] | None = None,
    *,
    config_path: Path | None = None,
) -> dict[str, pd.DataFrame]:
    _ensure_data_step()
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


def load_unallocated_mbank(
    assets_date: date,
    config: dict[str, pd.DataFrame] | None = None,
    *,
    config_path: Path | None = None,
) -> pd.DataFrame:
    _ensure_data_step()
    if config is None:
        config = read_analyse_config(config_path)

    # Catalog rebuild also materializes unallocated for the same date.
    load_catalog_events(assets_date, config, config_path=config_path)

    config_file = get_config_file(config_path)
    r = DATA_STEP.obtain_dependent(
        roi_unallocated_resource(assets_date),
        _build_unallocated,
        config_file,
        assets_date=assets_date,
    )
    return add_mbank_consolidated_ymd_columns(r.data_frame())


def _build_allocation(
    config: dict[str, pd.DataFrame],
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    catalog = config["catalog"]
    catalog = catalog[catalog["enabled"].astype(bool)].sort_values("order")
    pool = load_mbank_pool()
    return allocate_catalog(pool, catalog, config["rules"], config["manual"])


def _build_catalog_events(
    source_file: Path | None = None,
    *,
    assets_date: date,
    **_kwargs,
) -> pd.DataFrame:
    config = read_analyse_config(source_file)
    events_by_asset, unallocated = _build_allocation(config)
    unallocated = add_mbank_consolidated_ymd_columns(unallocated)

    def _materialize_unallocated(**_kw) -> pd.DataFrame:
        return unallocated

    DATA_STEP.obtain(
        roi_unallocated_resource(assets_date),
        _materialize_unallocated,
    )
    _export_roi_mbank_excels(events_by_asset, unallocated, config["catalog"], assets_date)

    frames = [events for events in events_by_asset.values() if not events.empty]
    if not frames:
        return pd.DataFrame(columns=list(CashFlowEvent.COLUMN_ORDER))
    result = pd.concat(frames, ignore_index=True)
    CashFlowEvent.check_structure(result)
    return result


def _build_unallocated(
    source_file: Path | None = None,
    *,
    assets_date: date,
    **_kwargs,
) -> pd.DataFrame:
    config = read_analyse_config(source_file)
    _events_by_asset, unallocated = _build_allocation(config)
    return add_mbank_consolidated_ymd_columns(unallocated)


def _export_roi_mbank_excels(
    events_by_asset: dict[str, pd.DataFrame],
    unallocated: pd.DataFrame,
    catalog: pd.DataFrame,
    assets_date: date,
) -> None:
    from app_proc.export_product_excel import export_roi_mbank_excels

    export_roi_mbank_excels(
        events_by_asset,
        add_mbank_consolidated_ymd_columns(unallocated),
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
