# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from datetime import date
from pathlib import Path

# Jedno źródło katalogu portfela + ROI (ex assets_1.xlsx + analyse_assets_config.xlsx).
A_CONFIG_FILE_NAME = "a_config.xlsx"
LEGACY_ASSETS_FILE_NAME = "assets_1.xlsx"
LEGACY_ANALYSE_CONFIG_FILE_NAME = "analyse_assets_config.xlsx"


def get_inwestycje_root() -> Path:
    root = Path.home() / "Dropbox" / "INWESTYCJE"
    assert root.is_dir()
    return root


def get_online_data_root() -> Path:
    data_root = get_inwestycje_root() / "assets"
    assert data_root.is_dir()
    return data_root


def get_a_config_file() -> Path:
    path = get_online_data_root() / A_CONFIG_FILE_NAME
    assert path.is_file(), f"Brak pliku {A_CONFIG_FILE_NAME} w {path.parent}"
    return path


def get_cash_pool_root() -> Path:
    return get_inwestycje_root() / "cash_pool"


def resolve_asset_dir(asset_id: str, typ: str) -> Path:
    """Katalog wyciągów / danych aktywa wg typ (cash_pool.* → cash_pool/, inaczej assets/)."""
    if str(typ).startswith("cash_pool."):
        return get_cash_pool_root() / asset_id
    return get_online_data_root() / asset_id


def _get_online_data_output() -> Path:
    data_root = get_inwestycje_root() / "product"
    assert data_root.is_dir()
    return data_root


def get_online_data_output(snapshot_date: date) -> Path:
    out = _get_online_data_output() / f"{snapshot_date:%Y-%m-%d}"
    out.mkdir(parents=True, exist_ok=True)
    return out
