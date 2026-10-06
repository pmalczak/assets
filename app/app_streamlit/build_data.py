from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from app_proc.snapshots import snapshots_directory, list_snapshot_files, load_snapshot
from importers.assets.data_model import AssetsDef


@st.cache_data(show_spinner="Wczytywanie snapshotow...")
def build_data(_schema: int = 4) -> dict[str, object]:
    """Ostatni snapshot do nagłówka dashboardu / zakładki Portfel. Bez historii wykresu."""
    del _schema
    snapshot_files = list_snapshot_files(snapshots_directory())
    if not snapshot_files:
        return {
            "latest_snapshot": pd.DataFrame(),
            "latest_snapshot_date": None,
            "snapshot_total_pln": 0.0,
        }

    latest_date, path = snapshot_files[-1]
    assets = load_snapshot(path)
    total = 0.0
    if not assets.empty and AssetsDef.VALUE_PLN in assets.columns:
        total = float(pd.to_numeric(assets[AssetsDef.VALUE_PLN], errors="coerce").fillna(0).sum())
    return {
        "latest_snapshot": assets,
        "latest_snapshot_date": latest_date,
        "snapshot_total_pln": total,
    }
