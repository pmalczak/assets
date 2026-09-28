# -*- coding: utf-8 -*-
"""Adapter katalogu ROI (roi_def / rules / manual)."""
from __future__ import annotations

from datetime import date

import pandas as pd

from portfolio_cf.adapters.base import empty_ledger, legacy_events_to_ledger
from portfolio_cf.coverage import InstrumentCoverage
from portfolio_cf.data_model import InstrumentCashFlow

VENUE = "catalog"

# Fallback gdy brak wiersza w ``assets`` / pustej ``waluta``.
# ``cash`` / ``rocky-iv`` (RODZAJ*=assets.cash) = waluta wyceny EUR — jak ROI katalog.
_FALLBACK_CURRENCY = {
    "cash": "EUR",
    "rocky-iv": "EUR",
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

    currencies = _catalog_currencies_from_assets()
    currencies.update(_FALLBACK_CURRENCY)
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


def _catalog_currencies_from_assets() -> dict[str, str]:
    """``assets.waluta`` → mapa instrument_id → waluta CF (PLN/EUR)."""
    try:
        from importers.assets.data_model import AssetsDef
        from importers.assets.read_assets import read_assets

        assets = read_assets()
    except Exception:
        return {}
    if assets is None or assets.empty:
        return {}
    if AssetsDef.ID not in assets.columns or AssetsDef.CURRENCY not in assets.columns:
        return {}
    out: dict[str, str] = {}
    for _, row in assets.iterrows():
        asset_id = str(row[AssetsDef.ID]).strip()
        currency = str(row.get(AssetsDef.CURRENCY) or "").strip().upper()
        if not asset_id or not currency:
            continue
        out[asset_id] = currency
    return out
