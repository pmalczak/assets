# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from data_step.data_step import DATA_STEP
from evaluators.evaluate_assets import evaluate_assets
from fx.data_model import LastFx
from importers.assets.data_model import AssetsDef, AssetsFile
from importers.assets.read_assets import read_assets
from app_proc.check_wrong_catalogs import check_wrong_catalogs
from app_proc.data_root import get_online_data_root
from app_proc.export_product_excel import export_assets_evaluation
from nbp_fx_repo.nbp_fx_repository import NBP_API_EUR, NbpFxRepository

ASSETS_SNAPSHOT_STEP = "09 assets"
PORTFOLIO_VALUATION_DATE = "data_wyceny_portfela"


def calculate_assets(
    valuation_date: date | None = None,
    force_read_all_data: bool = False,
) -> pd.DataFrame:
    if valuation_date is None:
        valuation_date = date.today()

    local_data_steps_root = Path(__file__).parent.parent
    DATA_STEP.init_steps(root=local_data_steps_root)

    if force_read_all_data:
        DATA_STEP.force_read_data()

    assets_resorce = assets_snapshot_resource(valuation_date)
    result = DATA_STEP.obtain(
        assets_resorce,
        _build_assets_snapshot,
        valuation_date=valuation_date,
    )
    assets = result.data_frame()
    export_assets_evaluation(assets, valuation_date)
    return assets


def _build_assets_snapshot(valuation_date: date) -> pd.DataFrame:
    data_root = get_online_data_root()

    metadata_root: Path = DATA_STEP.metadata.get_metadata_root() / "fx"
    if not metadata_root.is_dir():
        metadata_root.mkdir()

    fx_repo = NbpFxRepository(target_directory=metadata_root, min_year=2005)
    fx_rates = fx_repo.update_to_date()
    fx_rates = fx_rates[[NBP_API_EUR]]

    assets = read_assets()
    check_wrong_catalogs(data_root, assets)
    assets = evaluate_assets(data_root, assets, fx_rates, valuation_date)

    return _finalize_assets_snapshot(assets, valuation_date)


def _finalize_assets_snapshot(assets: pd.DataFrame, valuation_date: date) -> pd.DataFrame:
    result = assets.sort_values(by=[AssetsFile.GROUP, AssetsFile.ID])
    result = result[result[AssetsDef.VALUE] != 0]
    result = result.drop(columns=[AssetsDef.NOTES, LastFx.FX])
    result = result.copy()
    result[PORTFOLIO_VALUATION_DATE] = valuation_date.isoformat()
    return result


def assets_snapshot_resource(valuation_date: date) -> str:
    return f"{ASSETS_SNAPSHOT_STEP}/{valuation_date:%Y-%m-%d}.parquet"
