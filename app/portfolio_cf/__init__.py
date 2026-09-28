# -*- coding: utf-8 -*-
"""Ledger CF per instrument → alokacja do portfeli → XIRR (równolegle do legacy ROI)."""
from __future__ import annotations

from portfolio_cf.allocate import allocate_ledger_to_portfolio
from portfolio_cf.assemble import AssemblyResult, build_instrument_ledger
from portfolio_cf.coverage import CoverageStatus, InstrumentCoverage
from portfolio_cf.data_model import InstrumentCashFlow
from portfolio_cf.instrument_portfolio import portfolio_for_instrument
from portfolio_cf.instrument_summary import build_portfolio_instrument_summary
from portfolio_cf.products import (
    invalidate_portfolio_cf,
    load_assembly,
    load_portfolio_metrics_map,
    load_portfolio_xirr_map,
)
from portfolio_cf.xirr import (
    PortfolioXirrResult,
    RAP_TOTAL,
    build_portfolio_razem_row,
    compute_named_portfolio_metrics_map,
    compute_named_portfolio_xirr,
    compute_named_portfolio_xirr_map,
)

__all__ = [
    "AssemblyResult",
    "CoverageStatus",
    "InstrumentCashFlow",
    "InstrumentCoverage",
    "PortfolioXirrResult",
    "RAP_TOTAL",
    "allocate_ledger_to_portfolio",
    "build_instrument_ledger",
    "build_portfolio_instrument_summary",
    "build_portfolio_razem_row",
    "compute_named_portfolio_metrics_map",
    "compute_named_portfolio_xirr",
    "compute_named_portfolio_xirr_map",
    "invalidate_portfolio_cf",
    "load_assembly",
    "load_portfolio_metrics_map",
    "load_portfolio_xirr_map",
    "portfolio_for_instrument",
]
