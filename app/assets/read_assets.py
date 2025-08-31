# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from data_step.data_step import DATA_STEP


def read_assets(data_root: Path) -> pd.DataFrame:
    _in = 'assets.xlsx'
    _out = 'assets.parquet'
    r = DATA_STEP.obtain_dependent(_out, _read_assets, data_root / _in)
    result = r.data_frame()
    return result


def _read_assets(source_file = None) -> pd.DataFrame:
    # f = data_root / 'assets.xlsx'
    assert source_file.is_file()
    assets = pd.read_excel(source_file, sheet_name='assets')
    print(f'aktualizacja pliku {source_file}')
    return assets
