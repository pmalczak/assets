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
_NEAR_ZERO = 1e-9

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
    *,
    local_events_by_asset: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Jeden wiersz Razem dla widocznego summary (po filtrze Sprzedane).

    Kwoty = suma wierszy; XIRR = compute_xirr na concat CF + Σ terminal_unrealized;
    gdy podane ``local_events_by_asset`` — XIRR lokalny (FX_T), ``xirr_pln`` ze spot.
    Data wyceny = min niepustych dat wyceny elementów; is_sold = wszystkie sprzedane.
    """
    if summary is None or summary.empty:
        return pd.DataFrame()

    money = {col: float(summary[col].sum()) if col in summary.columns else 0.0 for col in _MONEY_COLUMNS}
    all_sold = bool(summary["is_sold"].all()) if "is_sold" in summary.columns else False
    eval_date = _min_evaluation_date(summary)

    asset_ids = summary["asset_id"].astype(str).tolist()
    terminal_unrealized = money["terminal_unrealized"]

    spot_pooled = _pool_cashflows(asset_ids, events_by_asset, valuation_date)
    spot_dates, spot_amounts = cashflows_for_xirr(
        spot_pooled, valuation_date, terminal_unrealized
    )
    xirr_spot = compute_xirr(spot_dates, spot_amounts)

    if local_events_by_asset is not None:
        local_pooled = _pool_cashflows(asset_ids, local_events_by_asset, valuation_date)
        local_dates, local_amounts = cashflows_for_xirr(
            local_pooled, valuation_date, terminal_unrealized
        )
        xirr = compute_xirr(local_dates, local_amounts)
        xirr_pln = xirr_spot
    else:
        xirr = xirr_spot
        xirr_pln = None

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
    if "roi_local" in summary.columns or "roi_fx" in summary.columns:
        roi_local = float(summary["roi_local"].sum()) if "roi_local" in summary.columns else 0.0
        roi_fx = float(summary["roi_fx"].sum()) if "roi_fx" in summary.columns else 0.0
        row["roi_local"] = round(roi_local)
        row["roi_fx"] = round(roi_fx)
        row["fx_share"] = (
            None
            if abs(money["roi_nominal"]) <= _NEAR_ZERO
            else roi_fx / money["roi_nominal"]
        )
    if xirr_pln is not None or "xirr_pln" in summary.columns:
        row["xirr_pln"] = xirr_pln
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
