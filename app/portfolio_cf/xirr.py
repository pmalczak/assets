# -*- coding: utf-8 -*-
"""XIRR nazwanego portfela na skonkatenowanych CF PLN + terminal NAV."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from app_proc.ui_prefs import SOLD_FILTER_SOLD
from portfolio_cf.allocate import allocate_ledger_to_portfolio
from portfolio_cf.assemble import AssemblyResult, build_instrument_ledger
from portfolio_cf.coverage import CoverageStatus, InstrumentCoverage
from portfolio_cf.data_model import InstrumentCashFlow
from portfolio_cf.instrument_portfolio import portfolio_for_instrument
from portfolio_cf.sold_status import (
    filter_coverage_by_sold,
    filter_ledger_by_sold,
    sold_filter_label,
)
from portfolios.assignment import nav_pln_for_portfolio
from roi.xirr import compute_xirr


@dataclass
class PortfolioXirrResult:
    portfolio: str
    valuation_date: date
    xirr: float | None
    terminal_pln: float
    cf_pln_sum: float
    roi_nominal_pln: float
    n_cashflows: int
    incomplete: bool
    warnings: list[str] = field(default_factory=list)
    uncovered: list[InstrumentCoverage] = field(default_factory=list)


def compute_named_portfolio_xirr(
    portfolio_name: str,
    valuation_date: date,
    *,
    assembly: AssemblyResult | None = None,
    snapshot: pd.DataFrame | None = None,
    terminal_pln: float | None = None,
    fx_rates: pd.DataFrame | None = None,
    sold_filter: str | None = None,
) -> PortfolioXirrResult:
    """Jeden XIRR na CF PLN instrumentów portfela + terminal NAV PLN.

    Uwzględnia globalny filtr sprzedane/niesprzedane (jak ROI Razem).
    UNCOVERED (po filtrze) z niezerowym NAV → warning + incomplete=True.
    """
    if assembly is None:
        assembly = build_instrument_ledger(
            valuation_date, fx_rates=fx_rates, snapshot=snapshot
        )

    mode = sold_filter if sold_filter is not None else sold_filter_label()
    subset = allocate_ledger_to_portfolio(assembly.ledger, portfolio_name)
    subset = filter_ledger_by_sold(
        subset, assembly.is_sold_by_instrument, sold_filter=mode
    )
    warnings = list(assembly.warnings)
    uncovered_in_portfolio = filter_coverage_by_sold(
        [
            item
            for item in assembly.coverage
            if item.status == CoverageStatus.UNCOVERED
            and portfolio_for_instrument(item.instrument_id) == portfolio_name
        ],
        assembly.is_sold_by_instrument,
        sold_filter=mode,
    )

    if terminal_pln is None:
        if mode == SOLD_FILTER_SOLD:
            # Sprzedane: terminal nerealiz. = 0 (jak w ROI per wiersz).
            terminal_pln = 0.0
        elif snapshot is not None and not snapshot.empty:
            terminal_pln = float(nav_pln_for_portfolio(snapshot, portfolio_name))
        else:
            terminal_pln = 0.0

    incomplete = False
    if uncovered_in_portfolio and abs(terminal_pln) > 1e-6:
        incomplete = True
        ids = ", ".join(item.instrument_id for item in uncovered_in_portfolio[:8])
        more = "" if len(uncovered_in_portfolio) <= 8 else "…"
        warnings.append(
            f"XIRR {portfolio_name}: niekompletne CF (UNCOVERED z NAV): {ids}{more}"
        )

    dates, amounts = _pln_series(subset, valuation_date, terminal_pln)
    xirr = compute_xirr(dates, amounts) if dates else None
    cf_sum = float(subset[InstrumentCashFlow.AMOUNT_PLN].sum()) if not subset.empty else 0.0

    return PortfolioXirrResult(
        portfolio=portfolio_name,
        valuation_date=valuation_date,
        xirr=xirr,
        terminal_pln=float(terminal_pln),
        cf_pln_sum=cf_sum,
        roi_nominal_pln=cf_sum + float(terminal_pln),
        n_cashflows=len(dates),
        incomplete=incomplete,
        warnings=warnings,
        uncovered=uncovered_in_portfolio,
    )


def _pln_series(
    ledger: pd.DataFrame,
    valuation_date: date,
    terminal_pln: float,
) -> tuple[list[date], list[float]]:
    dates: list[date] = []
    amounts: list[float] = []
    if ledger is not None and not ledger.empty:
        for _, row in ledger.iterrows():
            day = pd.Timestamp(row[InstrumentCashFlow.DATE]).date()
            dates.append(day)
            amounts.append(float(row[InstrumentCashFlow.AMOUNT_PLN]))
    if terminal_pln > 0:
        dates.append(valuation_date)
        amounts.append(float(terminal_pln))
    return _aggregate_by_date(dates, amounts)


def _aggregate_by_date(
    dates: list[date], amounts: list[float]
) -> tuple[list[date], list[float]]:
    totals: dict[date, float] = {}
    for day, amount in zip(dates, amounts):
        totals[day] = totals.get(day, 0.0) + amount
    ordered = sorted(totals)
    return ordered, [totals[day] for day in ordered]
