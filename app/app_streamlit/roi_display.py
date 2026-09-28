# -*- coding: utf-8 -*-
"""Wspólne formatowanie tabel summary ROI (zakładka ROI i Portfele)."""
from __future__ import annotations

import pandas as pd

from importers.assets.data_model import AssetsDef

ROI_DISPLAY_COLUMNS = {
    "asset_id": "Aktywo",
    "capex": "Inwestycja (CAPEX)",
    "opex": "Wydatki (OPEX)",
    "revenue": "Wplywy (REVENUES)",
    "terminal_realized": "Dezynwestycja (realiz.)",
    "terminal_unrealized": "Wycena (nerealiz.)",
    "roi_nominal": "ROI nominal",
    "xirr": "XIRR",
    "is_sold": "Sprzedane",
}
ROI_EVALUATION_DATE_LABEL = "Data wyceny"


def format_roi_summary_display(summary: pd.DataFrame) -> pd.DataFrame:
    """Tabela summary ROI → kolumny PL, kwoty jako tekst, XIRR jako %."""
    column_map = _roi_display_column_map(summary)
    keys = [key for key in column_map if key in summary.columns]
    display = summary[keys].rename(columns=column_map)
    if "instrument" in summary.columns:
        display["Aktywo"] = summary["instrument"].astype(str)
    skip_amount = {ROI_EVALUATION_DATE_LABEL, "Sprzedane", "XIRR"}
    for col in column_map.values():
        if col in skip_amount:
            continue
        if col in display.columns:
            display[col] = display[col].map(
                lambda v: f"{v:,}".replace(",", " ") if isinstance(v, (int, float)) else v
            )
    if "XIRR" in display.columns:
        display["XIRR"] = summary["xirr"].map(
            lambda v: f"{v * 100:.1f}%" if v is not None and pd.notna(v) else "—"
        )
    if "Sprzedane" in display.columns:
        # bool + pyarrow na Python 3.14 potrafi zabić proces Streamlit (segfault).
        display["Sprzedane"] = summary["is_sold"].map(lambda v: "tak" if bool(v) else "nie")
    return display


def _roi_display_column_map(summary: pd.DataFrame) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for key, label in ROI_DISPLAY_COLUMNS.items():
        mapping[key] = label
        if key == "terminal_unrealized" and AssetsDef.EVALUATION_DATE in summary.columns:
            mapping[AssetsDef.EVALUATION_DATE] = ROI_EVALUATION_DATE_LABEL
    return mapping
