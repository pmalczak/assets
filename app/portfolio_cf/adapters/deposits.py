# -*- coding: utf-8 -*-
"""Adapter depozytów Revolut + lokat mBank."""
from __future__ import annotations

from datetime import date

import pandas as pd

from portfolio_cf.adapters.base import empty_ledger, legacy_events_to_ledger
from portfolio_cf.coverage import InstrumentCoverage
from portfolio_cf.data_model import InstrumentCashFlow

VENUE = "deposits"


def _currency_for_deposit_id(asset_id: str) -> str:
    key = str(asset_id).lower()
    if "eur" in key:
        return "EUR"
    return "PLN"


def adapt_deposits_ledger(
    valuation_date: date,
    *,
    revolut_events: dict[str, pd.DataFrame] | None = None,
    mbank_events: dict[str, pd.DataFrame] | None = None,
    fx_rates: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, list[InstrumentCoverage], list[str]]:
    warnings: list[str] = []
    if revolut_events is None:
        from roi.revolut_deposit_roi import compute_revolut_deposit_roi

        _s, revolut_events, w = compute_revolut_deposit_roi(valuation_date)
        warnings.extend(w)
    if mbank_events is None:
        from roi.mbank_deposit_roi import compute_mbank_deposit_roi

        _s, mbank_events, w = compute_mbank_deposit_roi(valuation_date)
        warnings.extend(w)

    frames: list[pd.DataFrame] = []
    coverage: list[InstrumentCoverage] = []
    combined = {**(revolut_events or {}), **(mbank_events or {})}
    for asset_id, events in sorted(combined.items()):
        currency = _currency_for_deposit_id(asset_id)
        part, part_cov = legacy_events_to_ledger(
            {asset_id: events},
            venue=VENUE,
            currency=currency,
            valuation_date=valuation_date,
            fx_rates=fx_rates,
        )
        coverage.extend(part_cov)
        if not part.empty:
            frames.append(part)

    if not frames:
        return empty_ledger(), coverage, warnings
    out = pd.concat(frames, ignore_index=True)
    InstrumentCashFlow.check_structure(out)
    return out, coverage, warnings
