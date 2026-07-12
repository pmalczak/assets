# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date

import pandas as pd

from evaluators.valuation_date import filter_excel_rows_on_or_before, filter_on_or_before
from importers.assets.data_model import OperationDomain, Properties
from roi.categories import CLOSING
from roi.data_model import CashFlowEvent


def is_asset_sold(
    asset_id: str,
    cashflows: pd.DataFrame,
    properties_sheet: pd.DataFrame | None,
    valuation_date: date,
) -> bool:
    filtered = filter_excel_rows_on_or_before(cashflows, CashFlowEvent.DATE, valuation_date)
    if not filtered.empty:
        closing = filtered[filtered[CashFlowEvent.CATEGORY] == CLOSING]
        if not closing.empty:
            return True

    if properties_sheet is None or properties_sheet.empty:
        return False

    asset_props = properties_sheet[properties_sheet[Properties.ID] == asset_id]
    if asset_props.empty:
        return False

    sold = asset_props[asset_props[Properties.OPERATION] == OperationDomain.SOLD]
    if sold.empty:
        return False

    sold = filter_excel_rows_on_or_before(sold, Properties.DATE, valuation_date)
    return not sold.empty


def resolve_terminal_value(
    asset_id: str,
    cashflows: pd.DataFrame,
    properties_sheet: pd.DataFrame | None,
    valuation_date: date,
) -> tuple[float, float, list[str]]:
    warnings: list[str] = []
    filtered = filter_excel_rows_on_or_before(cashflows, CashFlowEvent.DATE, valuation_date)

    if is_asset_sold(asset_id, cashflows, properties_sheet, valuation_date):
        terminal_realized = float(
            filtered.loc[filtered[CashFlowEvent.CATEGORY] == CLOSING, CashFlowEvent.AMOUNT].sum()
        )
        return terminal_realized, 0.0, warnings

    terminal_unrealized = _latest_property_value(asset_id, properties_sheet, valuation_date, warnings)
    return 0.0, terminal_unrealized, warnings


def _latest_property_value(
    asset_id: str,
    properties_sheet: pd.DataFrame | None,
    valuation_date: date,
    warnings: list[str],
) -> float:
    if properties_sheet is None or properties_sheet.empty:
        warnings.append(f"Brak arkusza properties dla {asset_id!r}.")
        return 0.0

    asset_props = properties_sheet[properties_sheet[Properties.ID] == asset_id].copy()
    if asset_props.empty:
        warnings.append(f"Brak wyceny properties dla {asset_id!r}.")
        return 0.0

    open_props = asset_props[asset_props[Properties.OPERATION] != OperationDomain.SOLD]
    open_props = filter_excel_rows_on_or_before(open_props, Properties.DATE, valuation_date)
    if open_props.empty:
        warnings.append(f"Brak wyceny properties dla {asset_id!r} na date {valuation_date}.")
        return 0.0

    latest = open_props.sort_values(Properties.DATE, ascending=False).iloc[0]
    return float(latest[Properties.VALUE])
