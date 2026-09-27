# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
import math

import pandas as pd

from roi.data_model import CashFlowEvent

_DAYS_PER_YEAR = 365.0
_DEFAULT_GUESS = 0.1
_TOLERANCE = 1e-7
_MAX_ITERATIONS = 100
_NPV_OK = 1e-4
# Kolejność po `guess` z wywołania — długie serie (np. 0 PŁYNNY) często rozjeżdżają Newtona z 0.1.
_FALLBACK_GUESSES = (0.05, 0.0, 0.02, 0.2, -0.05, 0.5, -0.2, 1.0, -0.5)
_BRACKET_GRID = (
    -0.99,
    -0.5,
    -0.2,
    -0.1,
    -0.05,
    0.0,
    0.01,
    0.02,
    0.03,
    0.05,
    0.08,
    0.1,
    0.15,
    0.2,
    0.3,
    0.5,
    1.0,
    2.0,
    5.0,
    10.0,
)
_BISECT_ITERATIONS = 80


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

    seen: set[float] = set()
    for candidate in (guess, *_FALLBACK_GUESSES):
        if candidate in seen:
            continue
        seen.add(candidate)
        found = _newton_xirr(dates, amounts, candidate)
        if found is not None:
            return found

    return _bracket_bisect_xirr(dates, amounts)


def _newton_xirr(dates: list[date], amounts: list[float], guess: float) -> float | None:
    if not _is_valid_rate(guess):
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

    if abs(_xnpv(rate, dates, amounts)) < _NPV_OK and _is_valid_rate(rate):
        return rate
    return None


def _bracket_bisect_xirr(dates: list[date], amounts: list[float]) -> float | None:
    """Szuka zmiany znaku NPV na siatce, potem bisekcja."""
    samples: list[tuple[float, float]] = []
    for rate in _BRACKET_GRID:
        if not _is_valid_rate(rate):
            continue
        npv = _xnpv(rate, dates, amounts)
        if not math.isfinite(npv):
            continue
        if abs(npv) < _NPV_OK:
            return rate
        samples.append((rate, npv))

    for (lo, npv_lo), (hi, npv_hi) in zip(samples, samples[1:]):
        if npv_lo == 0.0:
            return lo
        if npv_lo * npv_hi < 0.0:
            return _bisect_xirr(dates, amounts, lo, hi)
    return None


def _bisect_xirr(
    dates: list[date],
    amounts: list[float],
    lo: float,
    hi: float,
) -> float | None:
    npv_lo = _xnpv(lo, dates, amounts)
    npv_hi = _xnpv(hi, dates, amounts)
    if not (math.isfinite(npv_lo) and math.isfinite(npv_hi)):
        return None
    if npv_lo * npv_hi > 0:
        return None

    for _ in range(_BISECT_ITERATIONS):
        mid = 0.5 * (lo + hi)
        npv_mid = _xnpv(mid, dates, amounts)
        if not math.isfinite(npv_mid):
            return None
        if abs(npv_mid) < _NPV_OK or abs(hi - lo) < _TOLERANCE:
            return mid
        if npv_lo * npv_mid <= 0:
            hi = mid
            npv_hi = npv_mid
        else:
            lo = mid
            npv_lo = npv_mid
    return 0.5 * (lo + hi)


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
