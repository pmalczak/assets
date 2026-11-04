# -*- coding: utf-8 -*-
"""Jednolity odczyt Excela: ``.xlsx`` → openpyxl, ``.xls`` → xlrd."""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def read_excel(path: Path | str, **kwargs) -> pd.DataFrame:
    """``pd.read_excel`` with engine chosen by suffix when not passed explicitly."""
    if "engine" not in kwargs:
        suffix = Path(path).suffix.lower()
        kwargs["engine"] = "xlrd" if suffix == ".xls" else "openpyxl"
    return pd.read_excel(path, **kwargs)
