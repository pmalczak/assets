# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from check_wrong_catalogs import check_wrong_catalogs
from data_root import get_online_data_root
from data_step.data_step import DATA_STEP
from evaluators.evaluate_assets import evaluate_assets
from fx.data_model import LastFx
from importers.assets.data_model import AssetsFile, AssetsDef
from importers.assets.read_assets import read_assets
from nbp_fx_repo.nbp_fx_repository import NbpFxRepository, NBP_API_EUR


def calculate_assets(force_read_all_data: bool = False) -> pd.DataFrame:
    local_data_steps_root = Path(__file__).parent.parent
    DATA_STEP.init_steps(root=local_data_steps_root)

    if force_read_all_data:
       DATA_STEP.force_read_data()

    data_root = get_online_data_root()

    metadata_root: Path = DATA_STEP.metadata.get_metadata_root() / 'fx'
    if not metadata_root.is_dir():
        metadata_root.mkdir()

    fx_repo = NbpFxRepository(target_directory=metadata_root, min_year=2005)
    fx_rates = fx_repo.update_to_date()
    fx_rates = fx_rates[[NBP_API_EUR]]

    assets = read_assets()
    check_wrong_catalogs(data_root, assets)
    assets = evaluate_assets(data_root, assets, fx_rates)

    assets = assets.sort_values(by=[AssetsFile.GROUP, AssetsFile.ID])
    assets = assets[assets[AssetsDef.VALUE] != 0]
    assets = assets.drop(columns=[AssetsDef.NOTES, LastFx.FX])
    return assets
