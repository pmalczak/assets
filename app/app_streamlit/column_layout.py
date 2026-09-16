# -*- coding: utf-8 -*-
"""Kolejność kolumn wartości i dat w tabelach UI."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from importers.assets.data_model import AssetsDef

VALUE_THEN_CURRENCY_THEN_PLN = (
    AssetsDef.VALUE,
    AssetsDef.CURRENCY,
    AssetsDef.VALUE_PLN,
)

EVAL_THEN_FX_THEN_DAYS = (
    AssetsDef.EVALUATION_DATE,
    AssetsDef.VALUE_DATE,
    AssetsDef.DAYS_AFTER_VALUATION,
)

_DISPLAY_BLOCKS = (
    VALUE_THEN_CURRENCY_THEN_PLN,
    EVAL_THEN_FX_THEN_DAYS,
)


AMOUNT_DISPLAY_COLUMNS = (
    AssetsDef.VALUE,
    AssetsDef.VALUE_PLN,
)


def format_amount_display(value) -> str:
    """Kwota UI: spacje tysięcy, bez części dziesiętnej (jak RAP)."""
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return ""
    return f"{int(round(float(number))):,}".replace(",", " ")


def format_amount_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.columns.empty:
        return df
    out = df.copy()
    for name in AMOUNT_DISPLAY_COLUMNS:
        if name in out.columns:
            out[name] = out[name].map(format_amount_display)
    return out


def amount_column_config(df: pd.DataFrame, extra: dict | None = None) -> dict:
    """Kwoty (tekst ze spacjami tysięcy) wyrównane do prawej — jak liczby w RAP."""
    config: dict = {}
    if df is not None and not df.columns.empty:
        for name in AMOUNT_DISPLAY_COLUMNS:
            if name in df.columns:
                config[name] = st.column_config.TextColumn(alignment="right")
    if extra:
        config.update(extra)
    return config


def with_value_currency_pln_order(df: pd.DataFrame) -> pd.DataFrame:
    """Blok wartości, potem blok dat wyceny — bez gubienia pozostałych kolumn."""
    return with_assets_table_column_order(df)


def with_assets_table_column_order(df: pd.DataFrame) -> pd.DataFrame:
    """`wartość`→`waluta`→`wartość-pln`, potem `data wyceny`→`data-waluty`→`liczba dni od wyceny`."""
    if df is None or df.columns.empty:
        return df
    cols = [str(c) for c in df.columns]
    block_members = {
        name
        for block in _DISPLAY_BLOCKS
        for name in block
        if name in cols
    }
    if not block_members:
        return df
    insert_at = min(cols.index(name) for name in block_members)
    rest = [name for name in cols if name not in block_members]
    before = [name for name in rest if cols.index(name) < insert_at]
    after = [name for name in rest if cols.index(name) >= insert_at]
    assembled: list[str] = []
    for block in _DISPLAY_BLOCKS:
        assembled.extend(name for name in block if name in cols)
    return df.loc[:, before + assembled + after]
