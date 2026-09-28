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
    "roi_local": "ROI lokalny",
    "roi_fx": "ROI FX",
    "fx_share": "Udział FX",
    "xirr": "XIRR",
    "xirr_pln": "XIRR PLN",
    "is_sold": "Sprzedane",
}
ROI_EVALUATION_DATE_LABEL = "Data wyceny"

_PERCENT_LABELS = frozenset({"XIRR", "XIRR PLN", "Udział FX"})
_SKIP_AMOUNT = frozenset({ROI_EVALUATION_DATE_LABEL, "Sprzedane"}) | _PERCENT_LABELS


def format_roi_summary_display(summary: pd.DataFrame) -> pd.DataFrame:
    """Tabela summary ROI → kolumny PL, kwoty jako tekst, XIRR / udział FX jako %."""
    column_map = _roi_display_column_map(summary)
    keys = [key for key in column_map if key in summary.columns]
    display = summary[keys].rename(columns=column_map)
    if "instrument" in summary.columns:
        display["Aktywo"] = summary["instrument"].astype(str)
    for col in column_map.values():
        if col in _SKIP_AMOUNT:
            continue
        if col in display.columns:
            display[col] = display[col].map(
                lambda v: f"{v:,}".replace(",", " ") if isinstance(v, (int, float)) else v
            )
    if "XIRR" in display.columns:
        display["XIRR"] = summary["xirr"].map(_format_rate_pct)
    if "XIRR PLN" in display.columns and "xirr_pln" in summary.columns:
        display["XIRR PLN"] = summary["xirr_pln"].map(_format_rate_pct)
    if "Udział FX" in display.columns and "fx_share" in summary.columns:
        display["Udział FX"] = summary["fx_share"].map(_format_rate_pct)
    if "Sprzedane" in display.columns:
        # bool + pyarrow na Python 3.14 potrafi zabić proces Streamlit (segfault).
        display["Sprzedane"] = summary["is_sold"].map(lambda v: "tak" if bool(v) else "nie")
    return display


def _format_rate_pct(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "—"


def _roi_display_column_map(summary: pd.DataFrame) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for key, label in ROI_DISPLAY_COLUMNS.items():
        mapping[key] = label
        if key == "terminal_unrealized" and AssetsDef.EVALUATION_DATE in summary.columns:
            mapping[AssetsDef.EVALUATION_DATE] = ROI_EVALUATION_DATE_LABEL
    return mapping
