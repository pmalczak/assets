# -*- coding: utf-8 -*-
"""Mapa is_sold per instrument (z venue ROI) + filtr jak w zakładce ROI."""
from __future__ import annotations

from datetime import date

import pandas as pd

from app_proc.ui_prefs import SOLD_COLUMN, current_sold_filter, filter_by_sold
from portfolio_cf.coverage import InstrumentCoverage
from portfolio_cf.data_model import InstrumentCashFlow
from portfolio_cf.instrument_portfolio import portfolio_for_instrument


def build_instrument_sold_map(valuation_date: date) -> dict[str, bool]:
    """Zbiera is_sold z summary venue ROI (katalog, brokerzy, depozyty, obligacje)."""
    sold: dict[str, bool] = {}
    loaders = (
        _load_catalog_sold,
        _load_robo_sold,
        _load_degiro_sold,
        _load_xtb_sold,
        _load_bonds_sold,
        _load_revolut_deposits_sold,
        _load_mbank_deposits_sold,
    )
    for loader in loaders:
        try:
            sold.update(loader(valuation_date))
        except Exception:
            continue
    return sold


def is_instrument_sold(
    instrument_id: str,
    sold_by_instrument: dict[str, bool] | None,
) -> bool:
    """Brak wpisu → traktuj jako niesprzedane (np. CASH, UNCOVERED bez venue ROI)."""
    if not sold_by_instrument:
        return False
    key = str(instrument_id).strip()
    if key in sold_by_instrument:
        return bool(sold_by_instrument[key])
    # CASH brokerski nie ma wiersza ROI — w filtrze jak otwarte.
    if key.endswith(":CASH"):
        return False
    return False


def filter_instrument_ids_by_sold(
    instrument_ids: list[str],
    sold_by_instrument: dict[str, bool] | None,
    *,
    sold_filter: str | None = None,
) -> list[str]:
    if not instrument_ids:
        return []
    frame = pd.DataFrame(
        {
            "instrument_id": instrument_ids,
            SOLD_COLUMN: [
                is_instrument_sold(item, sold_by_instrument) for item in instrument_ids
            ],
        }
    )
    filtered = filter_by_sold(frame, sold_filter)
    if filtered.empty:
        return []
    return filtered["instrument_id"].astype(str).tolist()


def filter_ledger_by_sold(
    ledger: pd.DataFrame,
    sold_by_instrument: dict[str, bool] | None,
    *,
    sold_filter: str | None = None,
) -> pd.DataFrame:
    if ledger is None or ledger.empty:
        return ledger
    ids = ledger[InstrumentCashFlow.INSTRUMENT_ID].astype(str)
    allowed = set(
        filter_instrument_ids_by_sold(
            sorted(ids.unique()),
            sold_by_instrument,
            sold_filter=sold_filter,
        )
    )
    return ledger.loc[ids.isin(allowed)].copy()


def filter_coverage_by_sold(
    coverage: list[InstrumentCoverage],
    sold_by_instrument: dict[str, bool] | None,
    *,
    portfolio_name: str | None = None,
    sold_filter: str | None = None,
) -> list[InstrumentCoverage]:
    items = coverage
    if portfolio_name is not None:
        items = [
            item
            for item in items
            if portfolio_for_instrument(item.instrument_id) == portfolio_name
        ]
    allowed = set(
        filter_instrument_ids_by_sold(
            [item.instrument_id for item in items],
            sold_by_instrument,
            sold_filter=sold_filter,
        )
    )
    return [item for item in items if item.instrument_id in allowed]


def sold_filter_label() -> str:
    try:
        return current_sold_filter()
    except Exception:
        from app_proc.ui_prefs import DEFAULT_SOLD_FILTER

        return DEFAULT_SOLD_FILTER


def _summary_sold_map(summary: pd.DataFrame) -> dict[str, bool]:
    if summary is None or summary.empty or "asset_id" not in summary.columns:
        return {}
    if "is_sold" not in summary.columns:
        return {str(asset_id): False for asset_id in summary["asset_id"].astype(str)}
    return {
        str(row["asset_id"]): bool(row["is_sold"])
        for _, row in summary.iterrows()
    }


def _load_catalog_sold(valuation_date: date) -> dict[str, bool]:
    from roi.compute_roi import compute_portfolio_roi

    summary, _events = compute_portfolio_roi(valuation_date)
    return _summary_sold_map(summary)


def _load_robo_sold(valuation_date: date) -> dict[str, bool]:
    from roi.broker_trading_roi import compute_revolut_robo_ticker_roi

    summary, _events, *_rest = compute_revolut_robo_ticker_roi(valuation_date)
    return _summary_sold_map(summary)


def _load_degiro_sold(valuation_date: date) -> dict[str, bool]:
    from roi.degiro_roi import compute_degiro_ticker_roi

    summary, _events, *_rest = compute_degiro_ticker_roi(valuation_date)
    return _summary_sold_map(summary)


def _load_xtb_sold(valuation_date: date) -> dict[str, bool]:
    from roi.xtb_roi import compute_xtb_ticker_roi

    summary, _events, *_rest = compute_xtb_ticker_roi(valuation_date)
    return _summary_sold_map(summary)


def _load_bonds_sold(valuation_date: date) -> dict[str, bool]:
    from roi.broker_obligacje_roi import compute_obligacje_broker_roi

    summary, _events, *_rest = compute_obligacje_broker_roi(valuation_date)
    return _summary_sold_map(summary)


def _load_revolut_deposits_sold(valuation_date: date) -> dict[str, bool]:
    from roi.revolut_deposit_roi import compute_revolut_deposit_roi

    summary, _events, *_rest = compute_revolut_deposit_roi(valuation_date)
    return _summary_sold_map(summary)


def _load_mbank_deposits_sold(valuation_date: date) -> dict[str, bool]:
    from roi.mbank_deposit_roi import compute_mbank_deposit_roi

    summary, _events, *_rest = compute_mbank_deposit_roi(valuation_date)
    return _summary_sold_map(summary)
