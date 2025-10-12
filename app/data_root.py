# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path


def get_online_data_root() -> Path:
    data_root = Path().home() / 'Dropbox' / 'INWESTYCJE' / 'assets'
    assert data_root.is_dir()
    return data_root
