# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from importers.assets.data_model import (
    AssetsFile,
    GOLD_COIN_PURCHASES_SHEET,
    GOLD_COIN_UNIT_PRICES_SHEET,
    GOLD_COIN_VALUATIONS_SHEET,
    GoldCoinUnitPrices,
    LEGACY_PROPERTIES_SHEET,
    PROPERTIES_VALUATIONS_SHEET,
    PropertyValuations,
)
from importers.assets.pool_id import (
    MBANK_EUR,
    MBANK_PLN,
    POOL_ID_COLUMN,
    POOL_IDS,
    REVOLUT_EUR,
    REVOLUT_PLN,
    assign_pool_id,
)
from app_proc.data_root import get_online_data_root
from data_step.data_step import DATA_STEP

ASSETS_FILE_NAME = "assets_1.xlsx"
ASSETS_PARQUET = "assets.parquet"

# Kolumny runtime — nie należą do schematu Excela / parquet źródłowego.
_RUNTIME_ASSET_COLUMNS = (POOL_ID_COLUMN,)

# Re-export dla kompatybilności importów.
__all__ = [
    "ASSETS_FILE_NAME",
    "ASSETS_PARQUET",
    "MBANK_EUR",
    "MBANK_PLN",
    "POOL_IDS",
    "REVOLUT_EUR",
    "REVOLUT_PLN",
    "assign_pool_id",
    "get_assets_file",
    "read_assets",
    "read_asset_sheet",
    "read_asset_sheet_optional",
    "GOLD_COIN_UNIT_PRICES_SHEET",
    "read_gold_coin_purchase_rules",
    "read_gold_coin_unit_prices",
    "read_gold_coin_valuations",
    "read_property_valuations",
]


def _drop_runtime_columns(df: pd.DataFrame) -> pd.DataFrame:
    drop = [c for c in _RUNTIME_ASSET_COLUMNS if c in df.columns]
    return df.drop(columns=drop) if drop else df


def read_assets() -> pd.DataFrame:
    _out = ASSETS_PARQUET

    r = DATA_STEP.obtain_dependent(_out, _read_assets, get_assets_file())
    result = _drop_runtime_columns(r.data_frame())
    AssetsFile.check_structure(result)
    return assign_pool_id(result)


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


def read_asset_sheet_optional(sheet_name: str) -> pd.DataFrame:
    """Jak read_asset_sheet, ale brak zakładki → pusta ramka (bez wyjątku)."""
    source_file = get_assets_file()
    assert source_file.is_file(), source_file
    try:
        return pd.read_excel(source_file, sheet_name=sheet_name)
    except ValueError:
        return pd.DataFrame()


def read_gold_coin_purchase_rules() -> pd.DataFrame:
    return read_asset_sheet(GOLD_COIN_PURCHASES_SHEET)


def read_gold_coin_valuations() -> pd.DataFrame:
    """Wartość całego holdingu (snapshot). Brak zakładki → pusta ramka."""
    return read_asset_sheet_optional(GOLD_COIN_VALUATIONS_SHEET)


def read_gold_coin_unit_prices() -> pd.DataFrame:
    """Ceny jednostkowe monet (ROI / MTM). Brak zakładki → pusta ramka."""
    source_file = get_assets_file()
    prices = read_asset_sheet_optional(GOLD_COIN_UNIT_PRICES_SHEET)
    if not prices.empty:
        GoldCoinUnitPrices.check_structure(prices, file=source_file)
    return prices


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
    # pool_id jest wyliczany w read_assets(); ignoruj jeśli ktoś dopisał do Excela.
    assets = _drop_runtime_columns(assets)
    AssetsFile.check_structure(assets)
    print(f'aktualizacja pliku {source_file}')
    return assets
