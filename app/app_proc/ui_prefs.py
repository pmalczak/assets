# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

import streamlit as st

from app_proc.data_steps_root import get_data_steps_root

TAB_LABELS = ["Wykres portfela", "Raporty", "Wyszukiwanie transakcji", "ROI", "Import wyciągów"]
DEFAULT_TAB = "Raporty"
TABS_STATE_KEY = "app_assets_tab"

SLUG_TO_LABEL = {
    "wykres": "Wykres portfela",
    "raporty": "Raporty",
    "szukaj": "Wyszukiwanie transakcji",
    "roi": "ROI",
    "import": "Import wyciągów",
}
LABEL_TO_SLUG = {label: slug for slug, label in SLUG_TO_LABEL.items()}

LAST_TAB_FILE = "last_tab.txt"


def last_tab_path(prefs_root: Path | None = None) -> Path:
    root = prefs_root or (get_data_steps_root() / "_ui")
    return root / LAST_TAB_FILE


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
    save_last_tab(st.session_state[TABS_STATE_KEY])
