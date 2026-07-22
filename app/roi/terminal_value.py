# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date

import pandas as pd

from importers.assets.property_lifecycle import (
    is_property_closed,
    latest_valuation_on_date,
    load_property_close_dates,
)
from importers.assets.read_assets import read_cash_sheet_valuations
from evaluators.valuation_date import filter_excel_rows_on_or_before
from roi.categories import CLOSING
from roi.config import read_analyse_config
from roi.data_model import CashFlowEvent
from roi.gold_terminal import is_gold_roi_asset, resolve_gold_terminal_unrealized

CASH_ROI_ASSET_ID = "cash"
_CASH_SHEET_DATE = "Data"
_CASH_SHEET_VALUE = "wartość"
_CASH_SHEET_CURRENCY = "waluta"


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

    if is_gold_roi_asset(asset_id, lookup_id):
        terminal_unrealized, gold_warnings = resolve_gold_terminal_unrealized(
            valuation_date,
            cashflows=filtered,
        )
        warnings.extend(gold_warnings)
        return 0.0, terminal_unrealized, warnings

    if _is_cash_roi_asset(asset_id, lookup_id):
        terminal_unrealized = _latest_cash_value(
            lookup_id,
            valuations,
            valuation_date,
            warnings,
            asset_id=asset_id,
        )
        return 0.0, terminal_unrealized, warnings

    terminal_unrealized = _latest_property_value(
        lookup_id,
        valuations,
        valuation_date,
        warnings,
        asset_id=asset_id,
    )
    return 0.0, terminal_unrealized, warnings


def _is_cash_roi_asset(asset_id: str | None, properties_id: str | None) -> bool:
    return (properties_id or asset_id) == CASH_ROI_ASSET_ID


def latest_cash_sheet_on_date(
    cash_sheet: pd.DataFrame | None,
    valuation_date: date,
    *,
    currency: str = "EUR",
) -> tuple[float, date] | None:
    """Ostatnia wycena z arkusza cash (Data ≤ valuation_date) dla waluty."""
    if cash_sheet is None or cash_sheet.empty:
        return None
    if _CASH_SHEET_DATE not in cash_sheet.columns or _CASH_SHEET_VALUE not in cash_sheet.columns:
        return None

    filtered = filter_excel_rows_on_or_before(cash_sheet, _CASH_SHEET_DATE, valuation_date)
    if filtered.empty:
        return None

    if _CASH_SHEET_CURRENCY in filtered.columns:
        cur = filtered[
            filtered[_CASH_SHEET_CURRENCY].astype("string").str.upper() == currency.upper()
        ]
        if cur.empty:
            return None
        filtered = cur

    latest = filtered.sort_values(_CASH_SHEET_DATE, ascending=False).iloc[0]
    value = pd.to_numeric(latest[_CASH_SHEET_VALUE], errors="coerce")
    if pd.isna(value):
        return None
    evaluation_date = pd.Timestamp(latest[_CASH_SHEET_DATE]).date()
    return float(value), evaluation_date


def _latest_cash_value(
    properties_id: str,
    valuations: pd.DataFrame | None,
    valuation_date: date,
    warnings: list[str],
    *,
    asset_id: str | None = None,
    cash_sheet: pd.DataFrame | None = None,
) -> float:
    """
    Terminal cash: ostatnia wycena ≤ valuation_date spośród arkusza `cash`
    i wiersza cash w properties-wyceny (ta sama semantyka co inne aktywa).
    """
    label = asset_id or properties_id
    candidates: list[tuple[float, date]] = []

    if cash_sheet is None:
        cash_sheet = read_cash_sheet_valuations()
    sheet_latest = latest_cash_sheet_on_date(cash_sheet, valuation_date)
    if sheet_latest is not None:
        candidates.append(sheet_latest)

    if valuations is not None and not valuations.empty:
        config = read_analyse_config()
        close_dates = load_property_close_dates(config["manual"], config["catalog"])
        props_latest = latest_valuation_on_date(
            valuations, properties_id, valuation_date, close_dates
        )
        if props_latest is not None:
            candidates.append(props_latest)

    if not candidates:
        warnings.append(
            f"Brak wyceny cash (arkusz cash / properties-wyceny) dla {label!r} "
            f"na date {valuation_date}."
        )
        return 0.0

    value, _evaluation_date = max(candidates, key=lambda item: item[1])
    return value


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
