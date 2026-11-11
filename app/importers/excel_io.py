# -*- coding: utf-8 -*-
"""Jednolity odczyt Excela: ``.xlsx`` → openpyxl, ``.xls`` → xlrd."""
from __future__ import annotations

import warnings
from pathlib import Path

import pandas as pd

# Pliki bez „default style” (częste przy eksporcie z arkuszy online) — openpyxl i tak
# stosuje własne defaulty; komunikat jest szumem, nie błędem odczytu.
_OPENPYXL_NO_DEFAULT_STYLE = (
    "Workbook contains no default style, apply openpyxl's default"
)


def silence_openpyxl_default_style_warning() -> None:
    """Idempotentny filtr na znany UserWarning openpyxl (stylesheet)."""
    warnings.filterwarnings(
        "ignore",
        message=_OPENPYXL_NO_DEFAULT_STYLE,
        category=UserWarning,
        module=r"openpyxl\.styles\.stylesheet",
    )


def read_excel(path: Path | str, **kwargs) -> pd.DataFrame:
    """``pd.read_excel`` with engine chosen by suffix when not passed explicitly."""
    if "engine" not in kwargs:
        suffix = Path(path).suffix.lower()
        kwargs["engine"] = "xlrd" if suffix == ".xls" else "openpyxl"
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=_OPENPYXL_NO_DEFAULT_STYLE,
            category=UserWarning,
        )
        return pd.read_excel(path, **kwargs)
