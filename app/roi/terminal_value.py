# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date

import pandas as pd

from importers.assets.property_lifecycle import (
    is_property_closed,
    latest_valuation_on_date,
    load_property_close_dates,
)
from evaluators.valuation_date import filter_excel_rows_on_or_before
from roi.categories import CLOSING
from roi.config import read_analyse_config
from roi.data_model import CashFlowEvent


def is_asset_sold(
    asset_id: str,
    cashflows: pd.DataFrame,
    valuations: pd.DataFrame | None,
    valuation_date: date,
    *,
    properties_id: str | None = None,
) -> bool:
    filtered = filter_excel_rows_on_or_before(cashflows, CashFlowEvent.DATE, valuation_date)
    if not filtered.empty:
        closing = filtered[filtered[CashFlowEvent.CATEGORY] == CLOSING]
        if not closing.empty:
            return True

    lookup_id = properties_id or asset_id
    config = read_analyse_config()
    close_dates = load_property_close_dates(config["manual"], config["catalog"])
    return is_property_closed(lookup_id, valuation_date, close_dates)


def resolve_terminal_value(
    asset_id: str,
    cashflows: pd.DataFrame,
    valuations: pd.DataFrame | None,
    valuation_date: date,
    *,
    properties_id: str | None = None,
) -> tuple[float, float, list[str]]:
    warnings: list[str] = []
    filtered = filter_excel_rows_on_or_before(cashflows, CashFlowEvent.DATE, valuation_date)
    lookup_id = properties_id or asset_id

    if is_asset_sold(
        asset_id,
        cashflows,
        valuations,
        valuation_date,
        properties_id=lookup_id,
    ):
        terminal_realized = float(
            filtered.loc[filtered[CashFlowEvent.CATEGORY] == CLOSING, CashFlowEvent.AMOUNT].sum()
        )
        return terminal_realized, 0.0, warnings

    terminal_unrealized = _latest_property_value(
        lookup_id,
        valuations,
        valuation_date,
        warnings,
        asset_id=asset_id,
    )
    return 0.0, terminal_unrealized, warnings


def _latest_property_value(
    properties_id: str,
    valuations: pd.DataFrame | None,
    valuation_date: date,
    warnings: list[str],
    *,
    asset_id: str | None = None,
) -> float:
    label = asset_id or properties_id
    if valuations is None or valuations.empty:
        warnings.append(f"Brak arkusza properties-wyceny dla {label!r}.")
        return 0.0

    config = read_analyse_config()
    close_dates = load_property_close_dates(config["manual"], config["catalog"])
    latest = latest_valuation_on_date(valuations, properties_id, valuation_date, close_dates)
    if latest is None:
        if is_property_closed(properties_id, valuation_date, close_dates):
            return 0.0
        warnings.append(f"Brak wyceny properties-wyceny dla {label!r} na date {valuation_date}.")
        return 0.0

    value, _evaluation_date = latest
    return value
