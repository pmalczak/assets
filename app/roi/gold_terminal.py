# -*- coding: utf-8 -*-
"""Terminal ROI dla złoto-monety: CAPEX z analyse rules + inventory po dacie → Σ qty×cena."""
from __future__ import annotations

from datetime import date

import pandas as pd

from evaluators.valuation_date import filter_excel_rows_on_or_before
from importers.assets.data_model import Inventory, UnitPriceEvaluation
from importers.assets.read_assets import read_inventory, read_unit_price_evaluation
from roi.categories import CAPEX
from roi.data_model import CashFlowEvent

GOLD_COINS_ROI_ASSET_ID = "zloto-monety"


class GoldInventoryJoinError(ValueError):
    """CAPEX złota bez jednoznacznego wiersza inventory."""


def is_gold_roi_asset(asset_id: str | None) -> bool:
    return asset_id == GOLD_COINS_ROI_ASSET_ID


def _normalize_day(value) -> pd.Timestamp | None:
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return None
    return pd.Timestamp(ts).normalize()


def _capex_inventory_context(event: pd.Series) -> str:
    day = _normalize_day(event[CashFlowEvent.DATE])
    date_s = day.strftime("%Y-%m-%d") if day is not None else str(event[CashFlowEvent.DATE])
    source = str(event.get(CashFlowEvent.SOURCE, "") or "")
    title = str(event.get(CashFlowEvent.TITLE, "") or "")
    counterparty = str(event.get(CashFlowEvent.COUNTERPARTY, "") or "")
    return f"date={date_s} source={source!r} title={title!r} counterparty={counterparty!r}"


def _missing_inventory_message(ctx: str, reason: str) -> str:
    return (
        f"Dla transakcji {ctx} Brak jest wpisu w tabeli 'inventory' dla CAPEX  "
        f"(powod={reason})."
    )


def holdings_from_inventory(
    inventory: pd.DataFrame,
    valuation_date: date,
) -> dict[str, float]:
    """Suma sztuk per instrument z inventory z Data ≤ valuation_date (snapshot bez CAPEX)."""
    if inventory is None or inventory.empty:
        return {}
    filtered = filter_excel_rows_on_or_before(inventory, Inventory.DATE, valuation_date)
    if filtered.empty:
        return {}
    holdings: dict[str, float] = {}
    for _, row in filtered.iterrows():
        instrument = str(row[Inventory.INSTRUMENT]).strip()
        qty = pd.to_numeric(row[Inventory.QUANTITY], errors="coerce")
        if not instrument or pd.isna(qty):
            continue
        holdings[instrument] = holdings.get(instrument, 0.0) + float(qty)
    return holdings


def holdings_from_capex_and_inventory(
    cashflows: pd.DataFrame,
    inventory: pd.DataFrame,
    valuation_date: date,
) -> tuple[dict[str, float], list[str]]:
    """
    Join CAPEX ↔ inventory po dacie.
    Udany join → sztuki/instrument.
    Brak / niejednoznaczne / niekompletne inventory → GoldInventoryJoinError.
    """
    holdings: dict[str, float] = {}

    if cashflows is None or cashflows.empty:
        return holdings, []

    filtered = filter_excel_rows_on_or_before(cashflows, CashFlowEvent.DATE, valuation_date)
    if filtered.empty:
        return holdings, []

    capex = filtered[filtered[CashFlowEvent.CATEGORY] == CAPEX]
    if capex.empty:
        return holdings, []

    inv_by_date: dict[pd.Timestamp, pd.DataFrame] = {}
    if inventory is not None and not inventory.empty:
        inv = inventory.copy()
        inv["_day"] = pd.to_datetime(inv[Inventory.DATE], errors="coerce").dt.normalize()
        inv = inv.dropna(subset=["_day"])
        for day, group in inv.groupby("_day", sort=False):
            inv_by_date[pd.Timestamp(day)] = group

    for _, event in capex.iterrows():
        ctx = _capex_inventory_context(event)
        day = _normalize_day(event[CashFlowEvent.DATE])

        if day is None:
            raise GoldInventoryJoinError(
                _missing_inventory_message(ctx, "invalid_capex_date")
            )

        group = inv_by_date.get(day)
        if group is None or group.empty:
            raise GoldInventoryJoinError(
                _missing_inventory_message(ctx, "no_inventory_row")
            )
        if len(group) > 1:
            raise GoldInventoryJoinError(
                _missing_inventory_message(
                    ctx, f"ambiguous_inventory_date, rows={len(group)}"
                )
            )

        row = group.iloc[0]
        instrument = str(row[Inventory.INSTRUMENT]).strip()
        qty = pd.to_numeric(row[Inventory.QUANTITY], errors="coerce")
        if not instrument or pd.isna(qty):
            raise GoldInventoryJoinError(
                _missing_inventory_message(ctx, "incomplete_inventory_row")
            )
        holdings[instrument] = holdings.get(instrument, 0.0) + float(qty)

    return holdings, []


def latest_unit_price(
    unit_prices: pd.DataFrame,
    instrument: str,
    valuation_date: date,
) -> float | None:
    if unit_prices is None or unit_prices.empty:
        return None

    filtered = filter_excel_rows_on_or_before(
        unit_prices, UnitPriceEvaluation.DATE, valuation_date
    )
    if filtered.empty:
        return None

    instrument_rows = filtered[
        filtered[UnitPriceEvaluation.INSTRUMENT].astype("string").str.strip() == instrument
    ]
    if instrument_rows.empty:
        return None

    latest = instrument_rows.sort_values(UnitPriceEvaluation.DATE, ascending=False).iloc[0]
    price = pd.to_numeric(latest[UnitPriceEvaluation.UNIT_PRICE], errors="coerce")
    if pd.isna(price):
        return None
    return float(price)


def mark_to_market(
    holdings: dict[str, float],
    unit_prices: pd.DataFrame,
    valuation_date: date,
) -> tuple[float, list[str]]:
    """Σ qty × cena; brak ceny → warning i 0 dla tego instrumentu."""
    warnings: list[str] = []
    if not holdings:
        return 0.0, warnings

    total = 0.0
    for instrument, qty in holdings.items():
        price = latest_unit_price(unit_prices, instrument, valuation_date)
        if price is None:
            warnings.append(
                f"Brak ceny jednostkowej dla instrumentu {instrument!r} "
                f"na date {valuation_date}."
            )
            continue
        total += qty * price
    return total, warnings


def resolve_gold_terminal_unrealized(
    valuation_date: date,
    *,
    cashflows: pd.DataFrame | None = None,
    holdings: dict[str, float] | None = None,
    unit_prices: pd.DataFrame | None = None,
    inventory: pd.DataFrame | None = None,
) -> tuple[float, list[str]]:
    """
    Terminal unrealized dla złoto-monety.

    Produkcja: CAPEX cashflows + inventory (join po dacie) + unit-price-evaluation.
    Testy mogą podać `holdings` / `unit_prices` bezpośrednio.
    """
    warnings: list[str] = []

    if holdings is None:
        if inventory is None:
            inventory = read_inventory()
        if cashflows is None:
            warnings.append(
                "Brak cashflow CAPEX dla zloto-monety — terminal qty×cena = 0."
            )
            holdings = {}
        else:
            holdings, join_warnings = holdings_from_capex_and_inventory(
                cashflows, inventory, valuation_date
            )
            warnings.extend(join_warnings)

    if unit_prices is None:
        unit_prices = read_unit_price_evaluation()
        if unit_prices.empty:
            warnings.append(
                "Brak arkusza unit-price-evaluation (ceny jednostkowe) — terminal = 0."
            )
            return 0.0, warnings

    if not unit_prices.empty:
        UnitPriceEvaluation.check_structure(unit_prices)

    value, mtm_warnings = mark_to_market(holdings, unit_prices, valuation_date)
    warnings.extend(mtm_warnings)
    return value, warnings
