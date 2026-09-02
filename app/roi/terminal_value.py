# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date

import pandas as pd

from importers.assets.property_lifecycle import (
    earliest_divestment_dates,
    is_property_closed,
    latest_valuation_on_date,
    load_property_close_dates,
)
from evaluators.valuation_date import filter_excel_rows_on_or_before
from roi.categories import DIVESTMENT
from roi.config import read_analyse_config
from roi.data_model import CashFlowEvent
from roi.gold_terminal import is_gold_roi_asset, resolve_gold_terminal_unrealized


def _sum_divestment(filtered: pd.DataFrame) -> float:
    if filtered.empty:
        return 0.0
    mask = filtered[CashFlowEvent.CATEGORY] == DIVESTMENT
    return float(filtered.loc[mask, CashFlowEvent.AMOUNT].sum())


def load_roi_aware_close_dates(
    valuation_date: date,
    config: dict | None = None,
) -> dict[str, date]:
    """Close dates: manual + DIVESTMENT z alokacji ROI (dla investment.property)."""
    from roi.roi_products import load_catalog_events

    if config is None:
        config = read_analyse_config()
    events_by_asset = load_catalog_events(valuation_date, config)
    frames = [frame for frame in events_by_asset.values() if not frame.empty]
    events = (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(columns=list(CashFlowEvent.COLUMN_ORDER))
    )
    return load_property_close_dates(config["manual"], config["catalog"], events=events)


def is_asset_sold(
    asset_id: str,
    cashflows: pd.DataFrame,
    valuations: pd.DataFrame | None,
    valuation_date: date,
) -> bool:
    """is_sold: property ⇔ DIVESTMENT≤data; cash ⇔ close z manual; nie broker qty."""
    del valuations
    asset_key = str(asset_id)

    # Catalog ROI: DIVESTMENT w CF tego aktywa = pełne wyjście.
    # ID nieruchomości (horbaczewskiego) jest w roi_def, nie jako wiersz assets.
    # Brokerzy nie idą przez compute_roi (tam is_sold ⇔ qty≈0).
    filtered = filter_excel_rows_on_or_before(cashflows, CashFlowEvent.DATE, valuation_date)
    close_date = earliest_divestment_dates(filtered).get(asset_key)
    if close_date is not None:
        return valuation_date >= close_date

    config = read_analyse_config()
    close_dates = load_property_close_dates(config["manual"], config["catalog"], events=filtered)
    return is_property_closed(asset_id, valuation_date, close_dates)


def resolve_terminal_value(
    asset_id: str,
    cashflows: pd.DataFrame,
    valuations: pd.DataFrame | None,
    valuation_date: date,
) -> tuple[float, float, list[str]]:
    warnings: list[str] = []
    filtered = filter_excel_rows_on_or_before(cashflows, CashFlowEvent.DATE, valuation_date)
    terminal_realized = _sum_divestment(filtered)

    if is_asset_sold(
        asset_id,
        cashflows,
        valuations,
        valuation_date,
    ):
        return terminal_realized, 0.0, warnings

    if is_gold_roi_asset(asset_id):
        terminal_unrealized, gold_warnings = resolve_gold_terminal_unrealized(
            valuation_date,
            cashflows=filtered,
        )
        warnings.extend(gold_warnings)
        return terminal_realized, terminal_unrealized, warnings

    terminal_unrealized = _latest_property_value(
        asset_id,
        valuations,
        valuation_date,
        warnings,
    )
    return terminal_realized, terminal_unrealized, warnings


def _latest_property_value(
    asset_id: str,
    valuations: pd.DataFrame | None,
    valuation_date: date,
    warnings: list[str],
) -> float:
    if valuations is None or valuations.empty:
        warnings.append(f"Brak arkusza asset-evaluation dla {asset_id!r}.")
        return 0.0

    config = read_analyse_config()
    close_dates = load_property_close_dates(config["manual"], config["catalog"])
    latest = latest_valuation_on_date(valuations, asset_id, valuation_date, close_dates)
    if latest is None:
        if is_property_closed(asset_id, valuation_date, close_dates):
            return 0.0
        warnings.append(f"Brak wyceny asset-evaluation dla {asset_id!r} na date {valuation_date}.")
        return 0.0

    value, _evaluation_date = latest
    return value
