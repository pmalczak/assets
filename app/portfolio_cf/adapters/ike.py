# -*- coding: utf-8 -*-
"""Adapter IKE: CF z arkuszy IKE-PM / IKE-GM (a_config)."""
from __future__ import annotations

from datetime import date

import pandas as pd

from portfolio_cf.adapters.base import empty_ledger, legacy_events_to_ledger
from portfolio_cf.coverage import InstrumentCoverage
from portfolio_cf.data_model import InstrumentCashFlow
from roi.ike_roi import VENUE, load_ike_events_by_asset

CURRENCY = "PLN"


def adapt_ike_ledger(
    valuation_date: date,
    *,
    events_by_asset: dict[str, pd.DataFrame] | None = None,
    fx_rates: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, list[InstrumentCoverage], list[str]]:
    warnings: list[str] = []
    if events_by_asset is None:
        events_by_asset = load_ike_events_by_asset(valuation_date)

    frames: list[pd.DataFrame] = []
    coverage: list[InstrumentCoverage] = []
    for asset_id, events in sorted(events_by_asset.items()):
        part, part_cov = legacy_events_to_ledger(
            {asset_id: events},
            venue=VENUE,
            currency=CURRENCY,
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
