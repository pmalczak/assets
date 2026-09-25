# -*- coding: utf-8 -*-
"""Adapter obligacji skarbowych (emisje)."""
from __future__ import annotations

from datetime import date

import pandas as pd

from portfolio_cf.adapters.base import empty_ledger, legacy_events_to_ledger
from portfolio_cf.coverage import InstrumentCoverage
from portfolio_cf.data_model import InstrumentCashFlow

VENUE = "bonds"
CURRENCY = "PLN"


def adapt_bonds_ledger(
    valuation_date: date,
    *,
    events_by_asset: dict[str, pd.DataFrame] | None = None,
    fx_rates: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, list[InstrumentCoverage], list[str]]:
    warnings: list[str] = []
    if events_by_asset is None:
        from roi.broker_obligacje_roi import compute_obligacje_broker_roi

        _summary, events_by_asset, load_warnings = compute_obligacje_broker_roi(valuation_date)
        warnings.extend(load_warnings)

    ledger, coverage = legacy_events_to_ledger(
        events_by_asset or {},
        venue=VENUE,
        currency=CURRENCY,
        valuation_date=valuation_date,
        fx_rates=fx_rates,
    )
    if ledger.empty:
        return empty_ledger(), coverage, warnings
    InstrumentCashFlow.check_structure(ledger)
    return ledger, coverage, warnings
