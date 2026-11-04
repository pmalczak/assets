# -*- coding: utf-8 -*-
"""Wspólna orchestracja ROI cykli brokerów udziałowych (DEGIRO / XTB)."""
from __future__ import annotations

from collections.abc import Callable
from datetime import date

import pandas as pd

from roi.broker_investment_cycles import (
    broker_code_from_instrument_id,
    is_closed_cycle_instrument_id,
)
from roi.broker_trading_roi import compute_ticker_roi, ticker_asset_id
from roi.compute_roi import roi_summary_to_row
from roi.data_model import CashFlowEvent
from roi.eps import QTY_EPS
from roi.statement_valuation_date import attach_evaluation_date


def empty_cashflow_events() -> pd.DataFrame:
    return pd.DataFrame(columns=list(CashFlowEvent.COLUMN_ORDER))


def summarize_broker_cycle_roi(
    *,
    broker_id: str,
    valuation_date: date,
    events_by_asset: dict[str, pd.DataFrame],
    terminal_by_code: dict[str, float],
    qty_by_code: dict[str, float],
    eval_date: str | None,
    instrument_name: Callable[[str], str],
) -> list[dict]:
    """Pętla cykli + pozycje open bez CF → wiersze summary (z kolumną ``instrument``)."""
    rows: list[dict] = []
    open_bases = {a for a in events_by_asset if not is_closed_cycle_instrument_id(a)}

    for cycle_id, events in sorted(events_by_asset.items()):
        code = broker_code_from_instrument_id(cycle_id)
        if is_closed_cycle_instrument_id(cycle_id):
            open_qty = 0.0
            last_price = 0.0
        else:
            terminal = float(terminal_by_code.get(code, 0.0))
            qty = float(qty_by_code.get(code, 0.0))
            open_qty = 1.0 if abs(qty) > QTY_EPS and terminal != 0.0 else 0.0
            last_price = terminal if open_qty else 0.0
        summary = compute_ticker_roi(
            cycle_id,
            events,
            valuation_date,
            open_qty=open_qty,
            last_price=last_price,
        )
        row = attach_evaluation_date(roi_summary_to_row(summary), eval_date)
        row["instrument"] = instrument_name(code)
        rows.append(row)

    for code in sorted(c for c in terminal_by_code if c):
        bare = ticker_asset_id(broker_id, code)
        if bare in open_bases:
            continue
        terminal = float(terminal_by_code.get(code, 0.0))
        qty = float(qty_by_code.get(code, 0.0))
        if abs(qty) <= QTY_EPS or terminal == 0.0:
            continue
        summary = compute_ticker_roi(
            bare,
            empty_cashflow_events(),
            valuation_date,
            open_qty=1.0,
            last_price=terminal,
        )
        row = attach_evaluation_date(roi_summary_to_row(summary), eval_date)
        row["instrument"] = instrument_name(code)
        rows.append(row)

    return rows


def append_closed_without_cashflows(
    rows: list[dict],
    *,
    broker_id: str,
    valuation_date: date,
    events_by_asset: dict[str, pd.DataFrame],
    closed_codes: set[str] | list[str],
    terminal_by_code: dict[str, float],
    qty_by_code: dict[str, float],
    eval_date: str | None,
    instrument_name: Callable[[str], str],
) -> None:
    """XTB: zamknięte w Closed Positions bez CF — pusty wiersz sold (mutuje ``rows``)."""
    open_bases = {a for a in events_by_asset if not is_closed_cycle_instrument_id(a)}
    for code in sorted(closed_codes):
        bare = ticker_asset_id(broker_id, code)
        if any(broker_code_from_instrument_id(a) == code for a in events_by_asset):
            continue
        if bare in open_bases:
            continue
        if code in terminal_by_code and abs(float(qty_by_code.get(code, 0.0))) > QTY_EPS:
            continue
        summary = compute_ticker_roi(
            bare,
            empty_cashflow_events(),
            valuation_date,
            open_qty=0.0,
            last_price=0.0,
        )
        row = attach_evaluation_date(roi_summary_to_row(summary), eval_date)
        row["instrument"] = instrument_name(code)
        rows.append(row)
