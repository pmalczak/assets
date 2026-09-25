# -*- coding: utf-8 -*-
"""Adapter Revolut Robo: tickery + CASH (TOP-UP + lustra BUY/SELL/DIV)."""
from __future__ import annotations

from datetime import date

import pandas as pd

from evaluators.evaluate_broker_revolut import filter_trading_on_or_before, parse_trading_number
from evaluators.valuation_date import filter_excel_rows_on_or_before
from importers.revolut.trading_data_model import DEFAULT_REVOLUT_ROBO_ASSET_ID, RevolutTradingFile
from portfolio_cf.adapters.base import (
    build_ledger_row,
    cash_leg_category_and_amount,
    empty_ledger,
    legacy_events_to_ledger,
    rows_to_ledger,
)
from portfolio_cf.coverage import CoverageStatus, InstrumentCoverage
from portfolio_cf.data_model import InstrumentCashFlow, cash_instrument_id
from roi.broker_trading_roi import build_broker_ticker_cashflows
from roi.categories import CAPEX, DIVESTMENT, REVENUES

VENUE = "robo"
CURRENCY = "EUR"


def adapt_robo_ledger(
    valuation_date: date,
    *,
    broker_id: str = DEFAULT_REVOLUT_ROBO_ASSET_ID,
    trading_df: pd.DataFrame | None = None,
    fx_rates: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, list[InstrumentCoverage], list[str]]:
    warnings: list[str] = []
    if trading_df is None:
        from roi.broker_trading_roi import _load_broker_trading

        trading_df, load_warnings = _load_broker_trading(broker_id)
        warnings.extend(load_warnings)

    filtered = filter_trading_on_or_before(trading_df, valuation_date)
    events = build_broker_ticker_cashflows(filtered, broker_id)
    ticker_ledger, coverage = legacy_events_to_ledger(
        events,
        venue=VENUE,
        currency=CURRENCY,
        valuation_date=valuation_date,
        fx_rates=fx_rates,
    )
    cash_ledger, cash_cov = _build_robo_cash_ledger(
        filtered, broker_id=broker_id, valuation_date=valuation_date, fx_rates=fx_rates
    )
    coverage.append(cash_cov)
    frames = [frame for frame in (ticker_ledger, cash_ledger) if not frame.empty]
    if not frames:
        return empty_ledger(), coverage, warnings
    out = pd.concat(frames, ignore_index=True)
    InstrumentCashFlow.check_structure(out)
    return out, coverage, warnings


def _build_robo_cash_ledger(
    trading_df: pd.DataFrame,
    *,
    broker_id: str,
    valuation_date: date,
    fx_rates: pd.DataFrame | None,
) -> tuple[pd.DataFrame, InstrumentCoverage]:
    cash_id = cash_instrument_id(broker_id)
    cov = InstrumentCoverage(
        instrument_id=cash_id,
        status=CoverageStatus.COVERED,
        reason="TOP-UP + lustra trade/div",
        venue=VENUE,
    )
    if trading_df is None or trading_df.empty:
        return empty_ledger(), cov

    rows: list[dict] = []
    for _, row in trading_df.iterrows():
        tx_type = row[RevolutTradingFile.TYPE]
        amount = parse_trading_number(row[RevolutTradingFile.TOTAL_AMOUNT])
        if amount is None:
            continue
        event_date = row[RevolutTradingFile.DATE]
        if pd.isna(event_date):
            continue

        if tx_type == RevolutTradingFile.TYPE_CASH_TOP_UP:
            rows.append(
                build_ledger_row(
                    instrument_id=cash_id,
                    event_date=event_date,
                    category=CAPEX,
                    amount=-abs(float(amount)),
                    currency=CURRENCY,
                    venue=VENUE,
                    source=broker_id,
                    description=str(tx_type),
                    title="CASH",
                    fx_rates=fx_rates,
                )
            )
            continue

        if tx_type == RevolutTradingFile.TYPE_ROBO_FEE:
            continue

        ticker = row.get(RevolutTradingFile.TICKER)
        if pd.isna(ticker) or not str(ticker).strip():
            continue
        if tx_type == RevolutTradingFile.TYPE_BUY:
            ticker_cat, ticker_amt = CAPEX, -abs(float(amount))
        elif tx_type == RevolutTradingFile.TYPE_SELL:
            ticker_cat, ticker_amt = DIVESTMENT, abs(float(amount))
        elif tx_type == RevolutTradingFile.TYPE_DIVIDEND:
            ticker_cat, ticker_amt = REVENUES, abs(float(amount))
        else:
            continue

        cash_cat, cash_amt = cash_leg_category_and_amount(ticker_cat, ticker_amt)
        rows.append(
            build_ledger_row(
                instrument_id=cash_id,
                event_date=event_date,
                category=cash_cat,
                amount=cash_amt,
                currency=CURRENCY,
                venue=VENUE,
                source=broker_id,
                description=f"cash-leg:{tx_type}",
                title=str(ticker).strip(),
                fx_rates=fx_rates,
            )
        )

    ledger = rows_to_ledger(rows)
    if ledger.empty:
        return ledger, cov
    return filter_excel_rows_on_or_before(ledger, InstrumentCashFlow.DATE, valuation_date), cov
