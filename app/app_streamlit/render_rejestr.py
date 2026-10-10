# -*- coding: utf-8 -*-
"""Zakładka Rejestr — podgląd stanów qty / inventory walorów."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from app_proc.rejestr_views import (
    LAYER_RUCHY,
    LAYER_STAN,
    REJESTR_ASSETS,
    RejestrAssetView,
    RejestrLayer,
    build_rejestr_asset,
)
from app_streamlit.column_layout import amount_column_config, format_amount_columns
from importers.assets.data_model import AssetsDef

_SCHEMA = 1
_ASSET_KEY = "rejestr_asset"
_LAYER_KEY = "rejestr_layer"


@st.cache_data(show_spinner="Ładowanie rejestru…")
def _load_asset(asset: str, as_of_iso: str, _schema: int = _SCHEMA) -> RejestrAssetView:
    return build_rejestr_asset(asset, date.fromisoformat(as_of_iso))


def render_rejestr() -> None:
    st.subheader("Rejestr")
    st.caption(
        "Stany qty walorów z a_config (złoto, IKE) oraz wyciągów "
        "(obligacje, DEGIRO, XTB, Robo) — tylko podgląd, bez edycji."
    )

    if st.button("Odśwież", key="rejestr_refresh"):
        _load_asset.clear()
        st.rerun()

    asset = st.pills(
        "Aktywo",
        options=REJESTR_ASSETS,
        default=REJESTR_ASSETS[0],
        required=True,
        key=_ASSET_KEY,
        width="stretch",
    )

    as_of = date.today()
    try:
        view = _load_asset(asset, as_of.isoformat())
    except Exception as exc:
        st.error(f"Nie udało się wczytać rejestru {asset}: {exc}")
        return

    layer = _selected_layer(view)
    _render_belka(layer)
    for warning in layer.warnings:
        st.warning(warning)

    display = format_amount_columns(layer.frame)
    if display is None or display.empty:
        st.info("Brak wierszy w tym widoku.")
        return

    st.dataframe(
        display,
        width="stretch",
        hide_index=True,
        column_config=amount_column_config(
            display,
            extra=_number_column_config(display),
        ),
    )


def _selected_layer(view: RejestrAssetView) -> RejestrLayer:
    if not view.has_ruchy or view.ruchy is None:
        return view.stan

    choice = st.pills(
        "Warstwa",
        options=[LAYER_STAN, LAYER_RUCHY],
        default=LAYER_STAN,
        required=True,
        key=_LAYER_KEY,
    )
    if choice == LAYER_RUCHY:
        return view.ruchy
    return view.stan


def _render_belka(layer: RejestrLayer) -> None:
    parts: list[str] = []
    if layer.as_of:
        parts.append(f"as_of **{layer.as_of}**")
    parts.append(f"**{layer.n_positions}** poz.")
    if layer.total_value is not None:
        cur = layer.value_currency or ""
        total_txt = f"{int(round(layer.total_value)):,}".replace(",", " ")
        parts.append(f"Σ {total_txt} {cur}".rstrip())
    for key, value in layer.extra.items():
        if isinstance(value, float):
            if abs(value - round(value)) < 1e-9:
                shown = str(int(round(value)))
            else:
                shown = f"{value:g}"
        else:
            shown = str(value)
        parts.append(f"{key} **{shown}**")
    st.markdown(" · ".join(parts))


def _number_column_config(df: pd.DataFrame) -> dict:
    config: dict = {}
    if df is None or df.empty:
        return config
    qty_like = {
        "quantity",
        "qty",
        "sztuki",
        "jednostki",
        "Liczba jednostek",
        "DOSTĘPNA LICZBA OBLIGACJI",
        "ZABLOKOWANA LICZBA OBLIGACJI",
        "LICZBA OBLIGACJI",
        "kurs",
        "unit_price",
        "avg_cost",
        "last_price",
    }
    for name in df.columns:
        if name in (AssetsDef.VALUE, AssetsDef.VALUE_PLN):
            continue
        if name in qty_like or str(name).endswith("price"):
            config[name] = st.column_config.NumberColumn(format="%.4f")
    return config
