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
from roi.gold_terminal import is_gold_roi_asset, resolve_gold_terminal_unrealized


def is_asset_sold(
    asset_id: str,
    cashflows: pd.DataFrame,
    valuations: pd.DataFrame | None,
    valuation_date: date,
) -> bool:
    del valuations  # API kompatybilne; zamknięcie z cashflows / manual
    filtered = filter_excel_rows_on_or_before(cashflows, CashFlowEvent.DATE, valuation_date)
    if not filtered.empty:
        closing = filtered[filtered[CashFlowEvent.CATEGORY] == CLOSING]
        if not closing.empty:
            return True

    config = read_analyse_config()
    close_dates = load_property_close_dates(config["manual"], config["catalog"])
    return is_property_closed(asset_id, valuation_date, close_dates)


def resolve_terminal_value(
    asset_id: str,
    cashflows: pd.DataFrame,
    valuations: pd.DataFrame | None,
    valuation_date: date,
) -> tuple[float, float, list[str]]:
    warnings: list[str] = []
    filtered = filter_excel_rows_on_or_before(cashflows, CashFlowEvent.DATE, valuation_date)

    if is_asset_sold(
        asset_id,
        cashflows,
        valuations,
        valuation_date,
    ):
        terminal_realized = float(
            filtered.loc[filtered[CashFlowEvent.CATEGORY] == CLOSING, CashFlowEvent.AMOUNT].sum()
        )
        return terminal_realized, 0.0, warnings

    if is_gold_roi_asset(asset_id):
        terminal_unrealized, gold_warnings = resolve_gold_terminal_unrealized(
            valuation_date,
            cashflows=filtered,
        )
        warnings.extend(gold_warnings)
        return 0.0, terminal_unrealized, warnings

    terminal_unrealized = _latest_property_value(
        asset_id,
        valuations,
        valuation_date,
        warnings,
    )
    return 0.0, terminal_unrealized, warnings


def _latest_property_value(
    asset_id: str,
    valuations: pd.DataFrame | None,
    valuation_date: date,
    warnings: list[str],
) -> float:
    if valuations is None or valuations.empty:
        warnings.append(f"Brak arkusza properties-wyceny dla {asset_id!r}.")
        return 0.0

    config = read_analyse_config()
    close_dates = load_property_close_dates(config["manual"], config["catalog"])
    latest = latest_valuation_on_date(valuations, asset_id, valuation_date, close_dates)
    if latest is None:
        if is_property_closed(asset_id, valuation_date, close_dates):
            return 0.0
        warnings.append(f"Brak wyceny properties-wyceny dla {asset_id!r} na date {valuation_date}.")
        return 0.0

    value, _evaluation_date = latest
    return value
