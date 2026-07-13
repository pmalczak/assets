# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from importers.assets.data_model import (
    AssetsFile,
    GOLD_COIN_PURCHASES_SHEET,
    GOLD_COIN_VALUATIONS_SHEET,
    LEGACY_PROPERTIES_SHEET,
    PROPERTIES_VALUATIONS_SHEET,
    PropertyValuations,
)
from app_proc.data_root import get_online_data_root
from data_step.data_step import DATA_STEP

ASSETS_FILE_NAME = "assets_1.xlsx"


def read_assets() -> pd.DataFrame:
    _out = 'assets.parquet'

    r = DATA_STEP.obtain_dependent(_out, _read_assets, get_assets_file())
    result = r.data_frame()
    AssetsFile.check_structure(result)
    return result


def get_assets_file() -> Path:
    """Zwraca sciezke pliku konfiguracji aktywow w katalogu get_online_data_root()."""
    data_root = get_online_data_root()
    assets_file = data_root / ASSETS_FILE_NAME
    assert assets_file.is_file(), f"Brak pliku {ASSETS_FILE_NAME} w {data_root}"
    return assets_file


def read_asset_sheet(sheet_name: str) -> pd.DataFrame:
    source_file = get_assets_file()
    assert source_file.is_file(), source_file
    return pd.read_excel(source_file, sheet_name=sheet_name)


def read_gold_coin_purchase_rules() -> pd.DataFrame:
    return read_asset_sheet(GOLD_COIN_PURCHASES_SHEET)


def read_gold_coin_valuations() -> pd.DataFrame:
    return read_asset_sheet(GOLD_COIN_VALUATIONS_SHEET)


def read_property_valuations() -> pd.DataFrame:
    source_file = get_assets_file()
    sheet_name = _property_valuations_sheet_name(source_file)
    valuations = pd.read_excel(source_file, sheet_name=sheet_name)
    PropertyValuations.check_structure(valuations, file=source_file)
    return valuations


def _property_valuations_sheet_name(source_file: Path) -> str:
    sheet_names = pd.ExcelFile(source_file).sheet_names
    if PROPERTIES_VALUATIONS_SHEET in sheet_names:
        return PROPERTIES_VALUATIONS_SHEET
    if LEGACY_PROPERTIES_SHEET in sheet_names:
        return LEGACY_PROPERTIES_SHEET
    raise ValueError(
        f"Brak arkusza {PROPERTIES_VALUATIONS_SHEET!r} ani {LEGACY_PROPERTIES_SHEET!r} w {source_file}"
    )


def _read_assets(source_file = None) -> pd.DataFrame:
    assert source_file.is_file()
    assets = pd.read_excel(source_file, sheet_name='assets')
    AssetsFile.check_structure(assets)
    print(f'aktualizacja pliku {source_file}')
    return assets
