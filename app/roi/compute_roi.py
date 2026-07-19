# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from evaluators.valuation_date import filter_excel_rows_on_or_before
from roi.categories import INFLOW, INVESTMENT, OUTFLOW
from roi.config import read_analyse_config
from roi.data_model import CashFlowEvent
from roi.terminal_value import is_asset_sold, resolve_terminal_value
from roi.xirr import cashflows_for_xirr, compute_xirr


@dataclass
class RoiSummary:
    asset_id: str
    capex: float
    opex: float
    revenue: float
    terminal_realized: float
    terminal_unrealized: float
    roi_nominal: float
    xirr: float | None
    is_sold: bool
    warnings: list[str] = field(default_factory=list)


def _aggregate_category(cashflows: pd.DataFrame, category: str) -> float:
    if cashflows.empty:
        return 0.0
    mask = cashflows[CashFlowEvent.CATEGORY] == category
    return float(cashflows.loc[mask, CashFlowEvent.AMOUNT].sum())


def compute_roi(
    asset_id: str,
    cashflows: pd.DataFrame,
    properties_sheet: pd.DataFrame | None,
    valuation_date: date,
    *,
    properties_id: str | None = None,
) -> RoiSummary:
    filtered = filter_excel_rows_on_or_before(cashflows, CashFlowEvent.DATE, valuation_date)
    lookup_id = properties_id or asset_id

    capex = _aggregate_category(filtered, INVESTMENT)
    opex = _aggregate_category(filtered, OUTFLOW)
    revenue = _aggregate_category(filtered, INFLOW)
    terminal_realized, terminal_unrealized, warnings = resolve_terminal_value(
        asset_id,
        cashflows,
        properties_sheet,
        valuation_date,
        properties_id=lookup_id,
    )

    flows_total = float(filtered[CashFlowEvent.AMOUNT].sum()) if not filtered.empty else 0.0
    roi_nominal = flows_total + terminal_unrealized
    sold = is_asset_sold(
        asset_id,
        cashflows,
        properties_sheet,
        valuation_date,
        properties_id=lookup_id,
    )

    xirr_dates, xirr_amounts = cashflows_for_xirr(filtered, valuation_date, terminal_unrealized)
    xirr = compute_xirr(xirr_dates, xirr_amounts)

    return RoiSummary(
        asset_id=asset_id,
        capex=capex,
        opex=opex,
        revenue=revenue,
        terminal_realized=terminal_realized,
        terminal_unrealized=terminal_unrealized,
        roi_nominal=roi_nominal,
        xirr=xirr,
        is_sold=sold,
        warnings=warnings,
    )


def roi_summary_to_row(summary: RoiSummary) -> dict[str, object]:
    return {
        "asset_id": summary.asset_id,
        "capex": round(summary.capex),
        "opex": round(summary.opex),
        "revenue": round(summary.revenue),
        "terminal_realized": round(summary.terminal_realized),
        "terminal_unrealized": round(summary.terminal_unrealized),
        "roi_nominal": round(summary.roi_nominal),
        "xirr": summary.xirr,
        "is_sold": summary.is_sold,
        "warnings": "; ".join(summary.warnings),
    }


def compute_portfolio_roi(
    valuation_date: date,
    config_path: Path | None = None,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    from roi.roi_products import load_catalog_events, load_roi_summary

    config = read_analyse_config(config_path)
    summary = load_roi_summary(valuation_date, config, config_path=config_path)
    events_by_asset = load_catalog_events(valuation_date, config, config_path=config_path)
    return summary, events_by_asset
