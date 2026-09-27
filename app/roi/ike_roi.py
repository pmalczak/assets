# -*- coding: utf-8 -*-
"""CF IKE z arkuszy inventory (IKE-PM / IKE-GM) — CAPEX / DIVESTMENT."""
from __future__ import annotations

from datetime import date

import pandas as pd

from evaluators.valuation_date import filter_excel_rows_on_or_before
from importers.assets.ike import (
    IkeInventory,
    asset_id_for_account,
    read_ike_inventory,
)
from roi.categories import CAPEX, DIVESTMENT
from roi.data_model import CashFlowEvent

VENUE = "ike"


def build_ike_cashflows(
    inventory: pd.DataFrame,
    asset_id: str,
) -> pd.DataFrame:
    """Wiersze inventory → CashFlowEvent dla jednego konta IKE.

    wartość > 0 → CAPEX (−abs); wartość < 0 lub jednostki < 0 → DIVESTMENT (+abs).
    """
    cols = list(CashFlowEvent.COLUMN_ORDER)
    if inventory is None or inventory.empty:
        return pd.DataFrame(columns=cols)

    rows: list[dict] = []
    for _, row in inventory.iterrows():
        event_date = _event_date(row.get(IkeInventory.DATE))
        if event_date is None:
            continue
        value = pd.to_numeric(row.get(IkeInventory.VALUE), errors="coerce")
        units = pd.to_numeric(row.get(IkeInventory.UNITS), errors="coerce")
        if pd.isna(value):
            continue
        value_f = float(value)
        units_f = 0.0 if pd.isna(units) else float(units)
        if abs(value_f) < 1e-12 and abs(units_f) < 1e-12:
            continue

        product = str(row.get(IkeInventory.PRODUCT) or "").strip()
        if value_f < 0 or units_f < 0:
            category = DIVESTMENT
            amount = abs(value_f)
        else:
            category = CAPEX
            amount = -abs(value_f)

        rows.append(
            {
                CashFlowEvent.ASSET_ID: str(asset_id),
                CashFlowEvent.DATE: event_date.isoformat(),
                CashFlowEvent.AMOUNT: amount,
                CashFlowEvent.CATEGORY: category,
                CashFlowEvent.SOURCE: VENUE,
                CashFlowEvent.DESCRIPTION: f"{product}; jednostki={units_f}",
                CashFlowEvent.TITLE: product,
                CashFlowEvent.COUNTERPARTY: "",
                CashFlowEvent.ACCOUNT_NUMBER: "",
            }
        )

    if not rows:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame(rows, columns=cols)
    CashFlowEvent.check_structure(out)
    return out


def load_ike_events_by_asset(
    valuation_date: date,
    *,
    inventory_by_account: dict[str, pd.DataFrame] | None = None,
) -> dict[str, pd.DataFrame]:
    """Mapa asset_id → CashFlowEvent dla pm_ike i gm_ike (po filtrze daty)."""
    accounts = ("pm", "gm")
    result: dict[str, pd.DataFrame] = {}
    for account in accounts:
        asset_id = asset_id_for_account(account)
        if inventory_by_account is not None and account in inventory_by_account:
            inv = inventory_by_account[account]
        else:
            inv = read_ike_inventory(account)
        filtered = filter_excel_rows_on_or_before(inv, IkeInventory.DATE, valuation_date)
        result[asset_id] = build_ike_cashflows(filtered, asset_id)
    return result


def _event_date(value) -> date | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, date) and not isinstance(value, pd.Timestamp):
        return value
    parsed = pd.Timestamp(value)
    if pd.isna(parsed):
        return None
    return parsed.date()
