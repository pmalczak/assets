# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date

import pandas as pd

from roi.data_model import CashFlowEvent

_DAYS_PER_YEAR = 365.0
_DEFAULT_GUESS = 0.1
_TOLERANCE = 1e-7
_MAX_ITERATIONS = 100


def cashflows_for_xirr(
    cashflows: pd.DataFrame,
    valuation_date: date,
    terminal_unrealized: float,
) -> tuple[list[date], list[float]]:
    """Przeplywy do XIRR: zdarzenia + wycena terminalna na date wyceny (otwarte aktywa)."""
    if cashflows.empty and terminal_unrealized <= 0:
        return [], []

    dates: list[date] = []
    amounts: list[float] = []
    for _, row in cashflows.iterrows():
        dates.append(pd.Timestamp(row[CashFlowEvent.DATE]).date())
        amounts.append(float(row[CashFlowEvent.AMOUNT]))

    if terminal_unrealized > 0:
        dates.append(valuation_date)
        amounts.append(float(terminal_unrealized))

    return _aggregate_by_date(dates, amounts)


def compute_xirr(
    dates: list[date],
    amounts: list[float],
    *,
    guess: float = _DEFAULT_GUESS,
) -> float | None:
    if len(dates) != len(amounts) or len(dates) < 2:
        return None

    has_positive = any(amount > 0 for amount in amounts)
    has_negative = any(amount < 0 for amount in amounts)
    if not has_positive or not has_negative:
        return None

    rate = guess
    for _ in range(_MAX_ITERATIONS):
        npv = _xnpv(rate, dates, amounts)
        derivative = _xnpv_derivative(rate, dates, amounts)
        if abs(derivative) < 1e-12:
            break

        next_rate = rate - npv / derivative
        if not _is_valid_rate(next_rate):
            break
        if abs(next_rate - rate) < _TOLERANCE and abs(npv) < _TOLERANCE:
            return next_rate
        rate = next_rate

    if abs(_xnpv(rate, dates, amounts)) < 1e-4 and _is_valid_rate(rate):
        return rate
    return None


def _aggregate_by_date(dates: list[date], amounts: list[float]) -> tuple[list[date], list[float]]:
    totals: dict[date, float] = {}
    for day, amount in zip(dates, amounts):
        totals[day] = totals.get(day, 0.0) + amount
    ordered = sorted(totals)
    return ordered, [totals[day] for day in ordered]


def _year_fraction(start: date, end: date) -> float:
    return (end - start).days / _DAYS_PER_YEAR


def _xnpv(rate: float, dates: list[date], amounts: list[float]) -> float:
    if not _is_valid_rate(rate):
        return float("inf")
    start = dates[0]
    total = 0.0
    for day, amount in zip(dates, amounts):
        years = _year_fraction(start, day)
        total += amount / (1.0 + rate) ** years
    return total


def _xnpv_derivative(rate: float, dates: list[date], amounts: list[float]) -> float:
    if not _is_valid_rate(rate):
        return 0.0
    start = dates[0]
    total = 0.0
    for day, amount in zip(dates, amounts):
        years = _year_fraction(start, day)
        total -= years * amount / (1.0 + rate) ** (years + 1.0)
    return total


def _is_valid_rate(rate: float) -> bool:
    return rate > -1.0 and abs(rate) < 1e6
