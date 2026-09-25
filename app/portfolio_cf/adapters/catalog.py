# -*- coding: utf-8 -*-
"""Adapter katalogu ROI (roi_def / rules / manual)."""
from __future__ import annotations

from datetime import date

import pandas as pd

from portfolio_cf.adapters.base import empty_ledger, legacy_events_to_ledger
from portfolio_cf.coverage import InstrumentCoverage
from portfolio_cf.data_model import InstrumentCashFlow

VENUE = "catalog"

# Waluta natywna per instrument katalogu (v1).
_INSTRUMENT_CURRENCY = {
    "cash": "EUR",
}


def adapt_catalog_ledger(
    valuation_date: date,
    *,
    events_by_asset: dict[str, pd.DataFrame] | None = None,
    fx_rates: pd.DataFrame | None = None,
    currency_by_instrument: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, list[InstrumentCoverage], list[str]]:
    warnings: list[str] = []
    if events_by_asset is None:
        from roi.compute_roi import compute_portfolio_roi

        _summary, events_by_asset = compute_portfolio_roi(valuation_date)

    currencies = dict(_INSTRUMENT_CURRENCY)
    if currency_by_instrument:
        currencies.update(currency_by_instrument)

    frames: list[pd.DataFrame] = []
    coverage: list[InstrumentCoverage] = []
    for asset_id, events in sorted(events_by_asset.items()):
        currency = currencies.get(str(asset_id), "PLN")
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
