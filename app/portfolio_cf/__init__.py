# -*- coding: utf-8 -*-
"""Ledger CF per instrument → alokacja do portfeli → XIRR (równolegle do legacy ROI)."""
from __future__ import annotations

from portfolio_cf.allocate import allocate_ledger_to_portfolio
from portfolio_cf.assemble import AssemblyResult, build_instrument_ledger
from portfolio_cf.coverage import CoverageStatus, InstrumentCoverage
from portfolio_cf.data_model import InstrumentCashFlow
from portfolio_cf.instrument_portfolio import portfolio_for_instrument
from portfolio_cf.xirr import PortfolioXirrResult, compute_named_portfolio_xirr

__all__ = [
    "AssemblyResult",
    "CoverageStatus",
    "InstrumentCashFlow",
    "InstrumentCoverage",
    "PortfolioXirrResult",
    "allocate_ledger_to_portfolio",
    "build_instrument_ledger",
    "compute_named_portfolio_xirr",
    "portfolio_for_instrument",
]
