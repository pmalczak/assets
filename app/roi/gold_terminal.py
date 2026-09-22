# -*- coding: utf-8 -*-
"""Terminal ROI dla złoto-monety: CAPEX + inventory po dacie → sztuki × 1oz × NBP × 0,99."""
from __future__ import annotations

from datetime import date

import pandas as pd

from evaluators.valuation_date import filter_excel_rows_on_or_before
from importers.assets.data_model import Inventory
from importers.assets.read_assets import read_inventory
from nbp_pl_api.nbp_gold_repository import gold_price_as_of
from roi.categories import CAPEX
from roi.data_model import CashFlowEvent

GOLD_COINS_ROI_ASSET_ID = "zloto-monety"
TROY_OUNCE_GRAMS = 31.1034768
# Szacunek wartości bieżącej: kurs NBP minus 1%, nie cena dilera.
GOLD_VALUE_FACTOR = 0.99
_ONE_OUNCE = "1oz"


class GoldInventoryJoinError(ValueError):
    """CAPEX złota bez jednoznacznego wiersza inventory."""


def is_gold_roi_asset(asset_id: str | None) -> bool:
    return asset_id == GOLD_COINS_ROI_ASSET_ID


def require_one_ounce(weight) -> float:
    """Waga monety. Tylko zapis ``1oz``; inaczej twardy błąd. Zwraca gramy."""
    token = str(weight).strip().lower().replace(" ", "")
    if token != _ONE_OUNCE:
        raise ValueError(
            f"Nieobsługiwana waga złota {weight!r}; dozwolone jest tylko '1oz'."
        )
    return TROY_OUNCE_GRAMS


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
        require_one_ounce(row[Inventory.WEIGHT])
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
        require_one_ounce(row[Inventory.WEIGHT])
        holdings[instrument] = holdings.get(instrument, 0.0) + float(qty)

    return holdings, []


def mark_to_market(
    holdings: dict[str, float],
    valuation_date: date,
    *,
    gold_prices: pd.DataFrame | None = None,
) -> tuple[float, date | None, list[str]]:
    """Σ sztuki × 31,1034768 g × NBP (PLN/g) × 0,99. Pusta pozycja → 0."""
    warnings: list[str] = []
    if not holdings:
        return 0.0, None, warnings

    price_date, pln_per_gram = gold_price_as_of(valuation_date, series=gold_prices)
    pieces = sum(holdings.values())
    value = pieces * TROY_OUNCE_GRAMS * pln_per_gram * GOLD_VALUE_FACTOR
    return value, price_date, warnings


def resolve_gold_terminal_unrealized(
    valuation_date: date,
    *,
    cashflows: pd.DataFrame | None = None,
    holdings: dict[str, float] | None = None,
    inventory: pd.DataFrame | None = None,
    gold_prices: pd.DataFrame | None = None,
) -> tuple[float, date | None, list[str]]:
    """
    Terminal unrealized dla złoto-monety.

    Produkcja: CAPEX cashflows + inventory (join po dacie) + cena NBP × 0,99.
    Testy mogą podać `holdings` / `gold_prices` bezpośrednio.
    Zwraca (wartość, data publikacji NBP, ostrzeżenia).
    """
    warnings: list[str] = []

    if holdings is None:
        if inventory is None:
            inventory = read_inventory()
        if cashflows is None:
            warnings.append(
                "Brak cashflow CAPEX dla zloto-monety — terminal NBP×0,99 = 0."
            )
            holdings = {}
        else:
            holdings, join_warnings = holdings_from_capex_and_inventory(
                cashflows, inventory, valuation_date
            )
            warnings.extend(join_warnings)

    value, price_date, mtm_warnings = mark_to_market(
        holdings,
        valuation_date,
        gold_prices=gold_prices,
    )
    warnings.extend(mtm_warnings)
    return value, price_date, warnings
