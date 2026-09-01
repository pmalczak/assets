# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

import pandas as pd

TAB_ASSETS = "Wartość aktywów"

TAB_LABELS = [
    TAB_ASSETS,
    "Wykres portfela",
    "ROI",
    "FX",
    "Global momentum",
    "Import wyciągów",
    "Wyszukiwanie transakcji",
    "Waliduj",
]
DEFAULT_TAB = TAB_ASSETS
TABS_STATE_KEY = "app_assets_tab"

SLUG_TO_LABEL = {
    "wykres": "Wykres portfela",
    "raporty": TAB_ASSETS,
    "szukaj": "Wyszukiwanie transakcji",
    "roi": "ROI",
    "roi-robo": "ROI",
    "roi-depozyty": "ROI",
    "roi-mbank-depozyty": "ROI",
    "roi-obligacje": "ROI",
    "roi-degiro": "ROI",
    "roi-xtb": "ROI",
    "fx": "FX",
    "global-momentum": "Global momentum",
    "import": "Import wyciągów",
    "waliduj": "Waliduj",
}
LABEL_TO_SLUG = {}
for _slug, _label in SLUG_TO_LABEL.items():
    LABEL_TO_SLUG.setdefault(_label, _slug)

LAST_TAB_FILE = "last_tab.txt"

SOLD_FILTER_ACTIVE = "Niesprzedane"
SOLD_FILTER_SOLD = "Sprzedane"
SOLD_FILTER_ALL = "Wszystkie"
SOLD_FILTER_LABELS = [SOLD_FILTER_ACTIVE, SOLD_FILTER_SOLD, SOLD_FILTER_ALL]
DEFAULT_SOLD_FILTER = SOLD_FILTER_ALL
SOLD_FILTER_STATE_KEY = "app_assets_sold_filter"
SOLD_FILTER_FILE = "sold_filter.txt"
SOLD_FILTER_SLUG_TO_LABEL = {
    "active": SOLD_FILTER_ACTIVE,
    "sold": SOLD_FILTER_SOLD,
    "all": SOLD_FILTER_ALL,
}
SOLD_FILTER_LABEL_TO_SLUG = {label: slug for slug, label in SOLD_FILTER_SLUG_TO_LABEL.items()}
SOLD_COLUMN = "is_sold"


def _st():
    import streamlit as st
    return st


def _prefs_root(prefs_root: Path | None) -> Path:
    if prefs_root is not None:
        return prefs_root
    from app_proc.data_steps_root import get_data_steps_root
    return get_data_steps_root() / "_ui"


def last_tab_path(prefs_root: Path | None = None) -> Path:
    return _prefs_root(prefs_root) / LAST_TAB_FILE


def load_last_tab(prefs_root: Path | None = None) -> str:
    path = last_tab_path(prefs_root)
    if not path.is_file():
        return DEFAULT_TAB

    slug = path.read_text(encoding="utf-8").strip()
    return SLUG_TO_LABEL.get(slug, DEFAULT_TAB)


def save_last_tab(label: str, prefs_root: Path | None = None) -> None:
    if label not in LABEL_TO_SLUG:
        return

    path = last_tab_path(prefs_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(LABEL_TO_SLUG[label], encoding="utf-8")


def on_tab_changed() -> None:
    save_last_tab(_st().session_state[TABS_STATE_KEY])


def sold_filter_path(prefs_root: Path | None = None) -> Path:
    return _prefs_root(prefs_root) / SOLD_FILTER_FILE


def load_sold_filter(prefs_root: Path | None = None) -> str:
    path = sold_filter_path(prefs_root)
    if not path.is_file():
        return DEFAULT_SOLD_FILTER

    slug = path.read_text(encoding="utf-8").strip()
    return SOLD_FILTER_SLUG_TO_LABEL.get(slug, DEFAULT_SOLD_FILTER)


def save_sold_filter(label: str, prefs_root: Path | None = None) -> None:
    if label not in SOLD_FILTER_LABEL_TO_SLUG:
        return

    path = sold_filter_path(prefs_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(SOLD_FILTER_LABEL_TO_SLUG[label], encoding="utf-8")


def on_sold_filter_changed() -> None:
    save_sold_filter(_st().session_state[SOLD_FILTER_STATE_KEY])


def current_sold_filter() -> str:
    return _st().session_state.get(SOLD_FILTER_STATE_KEY, DEFAULT_SOLD_FILTER)


def filter_by_sold(df: pd.DataFrame, label: str | None = None, *, column: str = SOLD_COLUMN) -> pd.DataFrame:
    """Zostaw wiersze wg globalnego filtra pozycji (is_sold). Brak kolumny = bez zmian."""
    mode = label if label is not None else current_sold_filter()
    slug = SOLD_FILTER_LABEL_TO_SLUG.get(mode, "all")
    if slug == "all" or df.empty or column not in df.columns:
        return df

    mask = df[column].map(lambda v: bool(v) if pd.notna(v) else False)
    if slug == "sold":
        return df.loc[mask].copy()
    return df.loc[~mask].copy()


def render_sold_filter_control() -> None:
    st = _st()
    if SOLD_FILTER_STATE_KEY not in st.session_state:
        st.session_state[SOLD_FILTER_STATE_KEY] = load_sold_filter()

    st.sidebar.radio(
        "Pozycje",
        options=SOLD_FILTER_LABELS,
        key=SOLD_FILTER_STATE_KEY,
        on_change=on_sold_filter_changed,
        help="Filtruje tabele ROI według flagi sprzedane (is_sold): niesprzedane, sprzedane albo wszystkie.",
    )
