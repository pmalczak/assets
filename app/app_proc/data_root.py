# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from datetime import date
from pathlib import Path


def get_online_data_root() -> Path:
    data_root = Path().home() / 'Dropbox' / 'INWESTYCJE' / 'assets'
    assert data_root.is_dir()
    return data_root


def _get_online_data_output() -> Path:
    data_root = Path().home() / 'Dropbox' / 'INWESTYCJE' / 'product'
    assert data_root.is_dir()
    return data_root


def get_online_data_output(snapshot_date: date) -> Path:
    out = _get_online_data_output() / f"{snapshot_date:%Y-%m-%d}"
    out.mkdir(parents=True, exist_ok=True)
    return out
