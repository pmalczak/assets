# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from importers.assets.data_model import AssetsFile
from main_proc.data_root import get_online_data_root
from data_step.data_step import DATA_STEP


def read_assets() -> pd.DataFrame:
    _out = 'assets.parquet'

    r = DATA_STEP.obtain_dependent(_out, _read_assets, get_assets_file())
    result = r.data_frame()
    AssetsFile.check_structure(result)
    return result


def get_assets_file() -> Path:
    data_root = get_online_data_root()
    _in = 'assets.xlsx'
    return data_root / _in


def _read_assets(source_file = None) -> pd.DataFrame:
    assert source_file.is_file()
    assets = pd.read_excel(source_file, sheet_name='assets')
    AssetsFile.check_structure(assets)
    print(f'aktualizacja pliku {source_file}')
    return assets
