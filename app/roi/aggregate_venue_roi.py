# -*- coding: utf-8 -*-
"""Agregat ROI soczewki (pilli): jeden wiersz Razem z XIRR na połączonych CF."""
from __future__ import annotations

from datetime import date

import pandas as pd

from evaluators.valuation_date import filter_excel_rows_on_or_before
from importers.assets.data_model import AssetsDef
from roi.compute_roi import RoiSummary, roi_summary_to_row
from roi.data_model import CashFlowEvent
from roi.xirr import cashflows_for_xirr, compute_xirr

VENUE_TOTAL_ASSET_ID = "Razem"

_MONEY_COLUMNS = (
    "capex",
    "opex",
    "revenue",
    "terminal_realized",
    "terminal_unrealized",
    "roi_nominal",
)


def aggregate_venue_roi(
    summary: pd.DataFrame,
    events_by_asset: dict[str, pd.DataFrame],
    valuation_date: date,
) -> pd.DataFrame:
    """Jeden wiersz Razem dla widocznego summary (po filtrze Sprzedane).

    Kwoty = suma wierszy; XIRR = compute_xirr na concat CF + Σ terminal_unrealized;
    Data wyceny = min niepustych dat wyceny elementów; is_sold = wszystkie sprzedane.
    """
    if summary is None or summary.empty:
        return pd.DataFrame()

    money = {col: float(summary[col].sum()) if col in summary.columns else 0.0 for col in _MONEY_COLUMNS}
    all_sold = bool(summary["is_sold"].all()) if "is_sold" in summary.columns else False
    eval_date = _min_evaluation_date(summary)

    asset_ids = summary["asset_id"].astype(str).tolist()
    pooled = _pool_cashflows(asset_ids, events_by_asset, valuation_date)
    terminal_unrealized = money["terminal_unrealized"]
    xirr_dates, xirr_amounts = cashflows_for_xirr(pooled, valuation_date, terminal_unrealized)
    xirr = compute_xirr(xirr_dates, xirr_amounts)

    row = roi_summary_to_row(
        RoiSummary(
            asset_id=VENUE_TOTAL_ASSET_ID,
            capex=money["capex"],
            opex=money["opex"],
            revenue=money["revenue"],
            terminal_realized=money["terminal_realized"],
            terminal_unrealized=terminal_unrealized,
            roi_nominal=money["roi_nominal"],
            xirr=xirr,
            is_sold=all_sold,
            evaluation_date=eval_date,
        )
    )
    if "instrument" in summary.columns:
        row["instrument"] = VENUE_TOTAL_ASSET_ID
    return pd.DataFrame([row])


def _min_evaluation_date(summary: pd.DataFrame) -> str | None:
    if AssetsDef.EVALUATION_DATE not in summary.columns:
        return None
    parsed = pd.to_datetime(summary[AssetsDef.EVALUATION_DATE], errors="coerce")
    valid = parsed.dropna()
    if valid.empty:
        return None
    return valid.min().date().isoformat()


def _pool_cashflows(
    asset_ids: list[str],
    events_by_asset: dict[str, pd.DataFrame],
    valuation_date: date,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for asset_id in asset_ids:
        events = events_by_asset.get(asset_id)
        if events is None or events.empty:
            continue
        filtered = filter_excel_rows_on_or_before(events, CashFlowEvent.DATE, valuation_date)
        if not filtered.empty:
            frames.append(filtered)
    if not frames:
        return pd.DataFrame(columns=list(CashFlowEvent.COLUMN_ORDER))
    return pd.concat(frames, ignore_index=True)
