# -*- coding: utf-8 -*-
"""OPEX poza ROI gdy nieruchomość nie miała charakteru inwestycyjnego."""
from __future__ import annotations

from datetime import date

import pandas as pd

from evaluators.valuation_date import to_iso_date_series
from roi.categories import OPEX
from roi.data_model import CashFlowEvent

# asset_id → (od, do) włącznie: w tym oknie OPEX nie wchodzi do CF / XIRR / ROI.
NON_INVESTMENT_OPEX_EXCLUSIONS: dict[str, tuple[date, date]] = {
    "kiemliczow_3": (date(2012, 6, 15), date(2020, 8, 30)),
    "kiemliczow_4": (date(2000, 3, 1), date(2021, 12, 31)),
}


def exclude_non_investment_opex(asset_id: str, cashflows: pd.DataFrame) -> pd.DataFrame:
    """Usuń OPEX z okna bez charakteru inwestycyjnego dla danego ``asset_id``."""
    if cashflows is None or cashflows.empty:
        return cashflows
    window = NON_INVESTMENT_OPEX_EXCLUSIONS.get(str(asset_id).strip())
    if window is None:
        return cashflows
    if CashFlowEvent.CATEGORY not in cashflows.columns or CashFlowEvent.DATE not in cashflows.columns:
        return cashflows

    start_s, end_s = window[0].isoformat(), window[1].isoformat()
    dates = to_iso_date_series(cashflows[CashFlowEvent.DATE])
    drop = (
        (cashflows[CashFlowEvent.CATEGORY] == OPEX)
        & dates.notna()
        & (dates >= start_s)
        & (dates <= end_s)
    )
    if not bool(drop.any()):
        return cashflows
    return cashflows.loc[~drop].copy()


def apply_non_investment_opex_exclusions(events_by_asset: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Zastosuj wyłączenia OPEX do mapy CF katalogu (per asset_id)."""
    return {
        asset_id: exclude_non_investment_opex(asset_id, events)
        for asset_id, events in events_by_asset.items()
    }
