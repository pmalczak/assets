# -*- coding: utf-8 -*-
"""Wspólna normalizacja legacy CashFlowEvent → wiersze InstrumentCashFlow."""
from __future__ import annotations

from datetime import date
from typing import Iterable

import pandas as pd

from evaluators.valuation_date import filter_excel_rows_on_or_before
from portfolio_cf.coverage import CoverageStatus, InstrumentCoverage
from portfolio_cf.data_model import InstrumentCashFlow
from portfolio_cf.fx import to_pln
from roi.categories import CAPEX, DIVESTMENT, OPEX, REVENUES, normalize_roi_category
from roi.data_model import CashFlowEvent


def empty_ledger() -> pd.DataFrame:
    return pd.DataFrame(columns=list(InstrumentCashFlow.COLUMN_ORDER))


def legacy_events_to_ledger(
    events_by_asset: dict[str, pd.DataFrame],
    *,
    venue: str,
    currency: str,
    valuation_date: date,
    fx_rates: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, list[InstrumentCoverage]]:
    """Z mapy asset_id → CashFlowEvent buduje ledger + COVERED per instrument."""
    rows: list[dict] = []
    coverage: list[InstrumentCoverage] = []
    for asset_id, events in sorted(events_by_asset.items()):
        coverage.append(
            InstrumentCoverage(
                instrument_id=str(asset_id),
                status=CoverageStatus.COVERED,
                reason="adapter venue",
                venue=venue,
            )
        )
        if events is None or events.empty:
            continue
        filtered = filter_excel_rows_on_or_before(events, CashFlowEvent.DATE, valuation_date)
        for _, event in filtered.iterrows():
            rows.append(
                _legacy_row_to_ledger_row(
                    event,
                    instrument_id=str(asset_id),
                    venue=venue,
                    currency=currency,
                    fx_rates=fx_rates,
                )
            )
    if not rows:
        return empty_ledger(), coverage
    out = pd.DataFrame(rows, columns=list(InstrumentCashFlow.COLUMN_ORDER))
    InstrumentCashFlow.check_structure(out)
    return out, coverage


def rows_to_ledger(rows: Iterable[dict]) -> pd.DataFrame:
    materialised = list(rows)
    if not materialised:
        return empty_ledger()
    out = pd.DataFrame(materialised, columns=list(InstrumentCashFlow.COLUMN_ORDER))
    InstrumentCashFlow.check_structure(out)
    return out


def build_ledger_row(
    *,
    instrument_id: str,
    event_date: date | str,
    category: str,
    amount: float,
    currency: str,
    venue: str,
    source: str = "",
    description: str = "",
    title: str = "",
    counterparty: str = "",
    account_number: str = "",
    fx_rates: pd.DataFrame | None = None,
) -> dict:
    day = _as_date(event_date)
    conversion = to_pln(float(amount), currency, day, fx_rates=fx_rates)
    return {
        InstrumentCashFlow.INSTRUMENT_ID: str(instrument_id),
        InstrumentCashFlow.DATE: day.isoformat(),
        InstrumentCashFlow.CATEGORY: normalize_roi_category(category),
        InstrumentCashFlow.AMOUNT: float(amount),
        InstrumentCashFlow.CURRENCY: str(currency).strip().upper(),
        InstrumentCashFlow.AMOUNT_PLN: conversion.amount_pln,
        InstrumentCashFlow.FX_RATE: conversion.fx_rate,
        InstrumentCashFlow.FX_DATE: conversion.fx_date,
        InstrumentCashFlow.VENUE: venue,
        InstrumentCashFlow.SOURCE: source,
        InstrumentCashFlow.DESCRIPTION: description,
        InstrumentCashFlow.TITLE: title,
        InstrumentCashFlow.COUNTERPARTY: counterparty,
        InstrumentCashFlow.ACCOUNT_NUMBER: account_number,
    }


def cash_leg_category_and_amount(ticker_category: str, ticker_amount: float) -> tuple[str, float]:
    """Strona gotówkowa trade'u: przeciwny znak do CF tickera (wewnątrz portfela netto 0).

    OPEX na tickerze FEE nie dostaje lustra na CASH (koszt ma zostać w portfelu).
    """
    cat = normalize_roi_category(ticker_category)
    amount = float(ticker_amount)
    if cat == OPEX:
        raise ValueError("OPEX nie ma lustra CASH — zostaje na tickerze FEE")
    if cat == CAPEX:
        return DIVESTMENT, abs(amount)
    if cat == DIVESTMENT:
        return CAPEX, -abs(amount)
    if cat == REVENUES:
        return CAPEX, -abs(amount)
    raise ValueError(f"Brak lustra CASH dla kategorii {cat!r}")


def _legacy_row_to_ledger_row(
    event: pd.Series,
    *,
    instrument_id: str,
    venue: str,
    currency: str,
    fx_rates: pd.DataFrame | None,
) -> dict:
    return build_ledger_row(
        instrument_id=instrument_id,
        event_date=event[CashFlowEvent.DATE],
        category=str(event[CashFlowEvent.CATEGORY]),
        amount=float(event[CashFlowEvent.AMOUNT]),
        currency=currency,
        venue=venue,
        source=str(event.get(CashFlowEvent.SOURCE) or venue),
        description=str(event.get(CashFlowEvent.DESCRIPTION) or ""),
        title=str(event.get(CashFlowEvent.TITLE) or ""),
        counterparty=str(event.get(CashFlowEvent.COUNTERPARTY) or ""),
        account_number=str(event.get(CashFlowEvent.ACCOUNT_NUMBER) or ""),
        fx_rates=fx_rates,
    )


def _as_date(value: date | str) -> date:
    if isinstance(value, date) and not isinstance(value, pd.Timestamp):
        return value
    parsed = pd.Timestamp(value)
    if pd.isna(parsed):
        raise ValueError(f"Nieparsowalna data CF: {value!r}")
    return parsed.date()
