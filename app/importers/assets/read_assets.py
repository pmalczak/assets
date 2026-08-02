# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from importers.assets.data_model import (
    ASSET_EVALUATION_SHEET,
    AssetsFile,
    INVENTORY_SHEET,
    Inventory,
    LEGACY_ASSET_EVALUATION_SHEET,
    LEGACY_INVENTORY_SHEET,
    LEGACY_PROPERTIES_SHEET,
    LEGACY_UNIT_PRICE_EVALUATION_SHEET,
    PropertyValuations,
    UNIT_PRICE_EVALUATION_SHEET,
    UnitPriceEvaluation,
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
from app_proc.data_root import A_CONFIG_FILE_NAME, get_a_config_file
from data_step.data_step import DATA_STEP

ASSETS_FILE_NAME = A_CONFIG_FILE_NAME
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
    "INVENTORY_SHEET",
    "UNIT_PRICE_EVALUATION_SHEET",
    "ASSET_EVALUATION_SHEET",
    "read_inventory",
    "read_unit_price_evaluation",
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
    """Ścieżka a_config.xlsx (katalog portfela + ROI) w get_online_data_root()."""
    return get_a_config_file()


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


def _first_existing_sheet(source_file: Path, candidates: tuple[str, ...]) -> str | None:
    sheet_names = set(pd.ExcelFile(source_file).sheet_names)
    for name in candidates:
        if name in sheet_names:
            return name
    return None


def read_inventory() -> pd.DataFrame:
    """Inventory zakupow (Data, instrument, waga, sztuki). Brak zakladki → pusta ramka."""
    source_file = get_assets_file()
    sheet = _first_existing_sheet(
        source_file, (INVENTORY_SHEET, LEGACY_INVENTORY_SHEET)
    )
    if sheet is None:
        return pd.DataFrame()
    inventory = pd.read_excel(source_file, sheet_name=sheet)
    if sheet == LEGACY_INVENTORY_SHEET and "moneta" in inventory.columns and Inventory.INSTRUMENT not in inventory.columns:
        inventory = inventory.rename(columns={"moneta": Inventory.INSTRUMENT})
    if not inventory.empty:
        Inventory.check_structure(inventory, file=source_file)
    return inventory


def read_unit_price_evaluation() -> pd.DataFrame:
    """Ceny jednostkowe instrumentow (ROI / MTM). Brak zakladki → pusta ramka."""
    source_file = get_assets_file()
    sheet = _first_existing_sheet(
        source_file, (UNIT_PRICE_EVALUATION_SHEET, LEGACY_UNIT_PRICE_EVALUATION_SHEET)
    )
    if sheet is None:
        return pd.DataFrame()
    prices = pd.read_excel(source_file, sheet_name=sheet)
    if sheet == LEGACY_UNIT_PRICE_EVALUATION_SHEET and "moneta" in prices.columns and UnitPriceEvaluation.INSTRUMENT not in prices.columns:
        prices = prices.rename(columns={"moneta": UnitPriceEvaluation.INSTRUMENT})
    if not prices.empty:
        UnitPriceEvaluation.check_structure(prices, file=source_file)
    return prices


def read_property_valuations() -> pd.DataFrame:
    source_file = get_assets_file()
    sheet_name = _asset_evaluation_sheet_name(source_file)
    valuations = pd.read_excel(source_file, sheet_name=sheet_name)
    PropertyValuations.check_structure(valuations, file=source_file)
    return valuations


def _asset_evaluation_sheet_name(source_file: Path) -> str:
    sheet = _first_existing_sheet(
        source_file,
        (ASSET_EVALUATION_SHEET, LEGACY_ASSET_EVALUATION_SHEET, LEGACY_PROPERTIES_SHEET),
    )
    if sheet is None:
        raise ValueError(
            f"Brak arkusza {ASSET_EVALUATION_SHEET!r} "
            f"(ani legacy {LEGACY_ASSET_EVALUATION_SHEET!r}/{LEGACY_PROPERTIES_SHEET!r}) "
            f"w {source_file}"
        )
    return sheet


def _read_assets(source_file=None) -> pd.DataFrame:
    assert source_file.is_file()
    assets = pd.read_excel(source_file, sheet_name='assets')
    # pool_id jest wyliczany w read_assets(); ignoruj jeśli ktoś dopisał do Excela.
    assets = _drop_runtime_columns(assets)
    AssetsFile.check_structure(assets)
    print(f'aktualizacja pliku {source_file}')
    return assets
