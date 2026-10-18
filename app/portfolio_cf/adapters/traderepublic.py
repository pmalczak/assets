# -*- coding: utf-8 -*-
"""Adapter depozytu Trade Republic (`p_traderepublic`)."""
from __future__ import annotations

from datetime import date

import pandas as pd

from portfolio_cf.adapters.base import empty_ledger, legacy_events_to_ledger
from portfolio_cf.coverage import InstrumentCoverage
from portfolio_cf.data_model import InstrumentCashFlow

VENUE = "traderepublic"


def adapt_traderepublic_ledger(
    valuation_date: date,
    *,
    events: dict[str, pd.DataFrame] | None = None,
    fx_rates: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, list[InstrumentCoverage], list[str]]:
    warnings: list[str] = []
    if events is None:
        from roi.traderepublic_deposit_roi import compute_traderepublic_roi

        _s, events, w = compute_traderepublic_roi(valuation_date)
        warnings.extend(w)

    if not events:
        return empty_ledger(), [], warnings

    frames: list[pd.DataFrame] = []
    coverage: list[InstrumentCoverage] = []
    for asset_id, asset_events in sorted(events.items()):
        part, part_cov = legacy_events_to_ledger(
            {asset_id: asset_events},
            venue=VENUE,
            currency="PLN",
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
