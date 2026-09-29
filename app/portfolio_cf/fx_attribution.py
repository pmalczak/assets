# -*- coding: utf-8 -*-
"""Separacja FX w ROI/XIRR portfela (constant FX_T vs spot FX_t).

Kanoniczna semantyka i słownik: ``Cursor_rules.md`` → sekcja *XIRR portfela a FX*.

Skrót::

    ROI_PLN   = Σ amount_pln + terminal_PLN
    ROI_local = Σ amount × FX_T + terminal_PLN
    ROI_FX    = ROI_PLN − ROI_local
    udział_FX = ROI_FX / ROI_PLN   # podpisany; None gdy ROI_PLN≈0

XIRR lokalny = seria ``amount × FX_T``; XIRR PLN = seria ``amount_pln``.
Bez osobnego XIRR(FX).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from nbp_fx_repo.nbp_fx_repository import NBP_API_EUR, NBP_API_PLN
from portfolio_cf.data_model import InstrumentCashFlow
from portfolio_cf.fx import to_pln


_NEAR_ZERO = 1e-9


@dataclass(frozen=True)
class FxRoiComponents:
    roi_pln: float
    roi_local: float
    roi_fx: float
    fx_share: float | None


def valuation_fx_rate(
    currency: str,
    valuation_date: date,
    *,
    fx_rates: pd.DataFrame | None = None,
) -> float:
    """Kurs NBP na datę wyceny (PLN → 1.0)."""
    code = str(currency or "").strip().upper()
    if code in {"", NBP_API_PLN, "PLN"}:
        return 1.0
    return float(
        to_pln(1.0, code, valuation_date, fx_rates=fx_rates).fx_rate
    )


def valuation_fx_rates(
    valuation_date: date,
    *,
    fx_rates: pd.DataFrame | None = None,
    currencies: set[str] | None = None,
) -> dict[str, float]:
    """Mapa waluta → FX_T (co najmniej PLN + EUR)."""
    codes = {NBP_API_PLN, NBP_API_EUR}
    if currencies:
        codes |= {str(c).strip().upper() for c in currencies if str(c).strip()}
    return {
        code: valuation_fx_rate(code, valuation_date, fx_rates=fx_rates)
        for code in codes
    }


def amount_local_pln(
    amount: float,
    currency: str,
    rates_at_t: dict[str, float],
) -> float:
    code = str(currency or "").strip().upper() or NBP_API_PLN
    rate = rates_at_t.get(code)
    if rate is None:
        raise ValueError(f"Brak FX_T dla waluty {code!r}")
    return float(amount) * float(rate)


def roi_fx_components(
    ledger: pd.DataFrame | None,
    terminal_pln: float,
    valuation_date: date,
    *,
    fx_rates: pd.DataFrame | None = None,
) -> FxRoiComponents:
    """ROI_PLN (spot), ROI_local (FX_T), ROI_FX i podpisany udział."""
    rates_t = _rates_for_ledger(ledger, valuation_date, fx_rates=fx_rates)
    cf_pln = 0.0
    cf_local = 0.0
    if ledger is not None and not ledger.empty:
        for _, row in ledger.iterrows():
            amount = float(row[InstrumentCashFlow.AMOUNT])
            currency = str(row.get(InstrumentCashFlow.CURRENCY) or NBP_API_PLN)
            cf_pln += float(row[InstrumentCashFlow.AMOUNT_PLN])
            cf_local += amount_local_pln(amount, currency, rates_t)
    terminal = float(terminal_pln)
    roi_pln = cf_pln + terminal
    roi_local = cf_local + terminal
    roi_fx = roi_pln - roi_local
    share = None if abs(roi_pln) <= _NEAR_ZERO else roi_fx / roi_pln
    return FxRoiComponents(
        roi_pln=roi_pln,
        roi_local=roi_local,
        roi_fx=roi_fx,
        fx_share=share,
    )


def local_pln_series(
    ledger: pd.DataFrame | None,
    valuation_date: date,
    terminal_pln: float,
    *,
    fx_rates: pd.DataFrame | None = None,
) -> tuple[list[date], list[float]]:
    """Seria CF w PLN przy stałym FX_T + terminal — do XIRR lokalnego."""
    rates_t = _rates_for_ledger(ledger, valuation_date, fx_rates=fx_rates)
    dates: list[date] = []
    amounts: list[float] = []
    if ledger is not None and not ledger.empty:
        for _, row in ledger.iterrows():
            day = pd.Timestamp(row[InstrumentCashFlow.DATE]).date()
            currency = str(row.get(InstrumentCashFlow.CURRENCY) or NBP_API_PLN)
            dates.append(day)
            amounts.append(
                amount_local_pln(
                    float(row[InstrumentCashFlow.AMOUNT]),
                    currency,
                    rates_t,
                )
            )
    if float(terminal_pln) > 0:
        dates.append(valuation_date)
        amounts.append(float(terminal_pln))
    return _aggregate_by_date(dates, amounts)


def spot_pln_series(
    ledger: pd.DataFrame | None,
    valuation_date: date,
    terminal_pln: float,
) -> tuple[list[date], list[float]]:
    """Seria CF amount_pln (FX_t) + terminal — dotychczasowy XIRR PLN."""
    dates: list[date] = []
    amounts: list[float] = []
    if ledger is not None and not ledger.empty:
        for _, row in ledger.iterrows():
            day = pd.Timestamp(row[InstrumentCashFlow.DATE]).date()
            dates.append(day)
            amounts.append(float(row[InstrumentCashFlow.AMOUNT_PLN]))
    if float(terminal_pln) > 0:
        dates.append(valuation_date)
        amounts.append(float(terminal_pln))
    return _aggregate_by_date(dates, amounts)


def fx_share(roi_fx: float, roi_pln: float) -> float | None:
    if abs(float(roi_pln)) <= _NEAR_ZERO:
        return None
    return float(roi_fx) / float(roi_pln)


def _rates_for_ledger(
    ledger: pd.DataFrame | None,
    valuation_date: date,
    *,
    fx_rates: pd.DataFrame | None,
) -> dict[str, float]:
    currencies: set[str] = set()
    if ledger is not None and not ledger.empty and InstrumentCashFlow.CURRENCY in ledger.columns:
        currencies = {
            str(c).strip().upper()
            for c in ledger[InstrumentCashFlow.CURRENCY].tolist()
            if str(c).strip()
        }
    return valuation_fx_rates(
        valuation_date, fx_rates=fx_rates, currencies=currencies
    )


def _aggregate_by_date(
    dates: list[date], amounts: list[float]
) -> tuple[list[date], list[float]]:
    totals: dict[date, float] = {}
    for day, amount in zip(dates, amounts):
        totals[day] = totals.get(day, 0.0) + amount
    ordered = sorted(totals)
    return ordered, [totals[day] for day in ordered]
