# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from analyse_assets.account_tx import AccountTx
from analyse_assets.accounts_pools import load_accounts_pool
from evaluators.valuation_date import filter_excel_rows_on_or_before
from importers.assets.instruments import InstrumentMap, load_instrument_map
from importers.assets.pool_id import REVOLUT_PLN
from roi.asset_dir import require_broker_asset_dir
from roi.eps import MONEY_EPS
from importers.xtb.data_model import (
    CASH_OP_DEPOSIT,
    CASH_OP_PURCHASE,
    CASH_OP_SALE,
    DEFAULT_XTB_ASSET_ID,
    TICKER_ROI_TYPES,
    XtbCashOperationsFile,
    XtbClosedPositionsFile,
    XtbOpenPositionsFile,
    classify_xtb_cash_type,
    is_xtb_cash_footer,
    xtb_instrument_id,
)
from importers.xtb.read_xtb import (
    latest_open_as_of,
    parse_xtb_date,
    read_xtb_cash,
    read_xtb_closed,
    read_xtb_open,
    xtb_open_position_rows,
)
from roi.broker_cycle_roi import (
    append_closed_without_cashflows,
    empty_cashflow_events,
    summarize_broker_cycle_roi,
)
from roi.broker_investment_cycles import (
    broker_code_from_instrument_id,
    partition_broker_cashflows,
)
from roi.broker_trading_roi import ticker_asset_id
from roi.categories import CAPEX, DIVESTMENT, REVENUES
from roi.data_model import CashFlowEvent
from roi.statement_valuation_date import evaluation_date_from_frame

# Soft reconcile: kartowe Deposit (Adyen) vs Opis XTB na revolut_pln.
RECONCILE_TOLERANCE_PLN = 0.01
_XTB_CARD_DEPOSIT_COMMENT = "adyen"
_REVOLUT_XTB_TITLE = r"\bxtb\b"


def compute_xtb_ticker_roi(
    valuation_date: date,
    *,
    broker_id: str = DEFAULT_XTB_ASSET_ID,
    cash_operations_df: pd.DataFrame | None = None,
    open_positions_df: pd.DataFrame | None = None,
    closed_positions_df: pd.DataFrame | None = None,
    instruments: InstrumentMap | None = None,
    pool_tx: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], list[str]]:
    warnings: list[str] = []
    if cash_operations_df is None or open_positions_df is None:
        asset_dir = _asset_dir(broker_id)
        if open_positions_df is None:
            open_positions_df = read_xtb_open(asset_dir, broker_id)
        if cash_operations_df is None:
            cash_operations_df, cash_warnings = read_xtb_cash(asset_dir, broker_id)
            warnings.extend(cash_warnings)
        if closed_positions_df is None:
            closed_positions_df = read_xtb_closed(asset_dir, broker_id)

    if closed_positions_df is None:
        closed_positions_df = pd.DataFrame()

    open_latest = latest_open_as_of(open_positions_df, valuation_date)
    eval_date = evaluation_date_from_frame(
        open_latest, XtbOpenPositionsFile.FILE_DATE, valuation_date
    )
    cash_operations_df = _filter_xtb_rows_on_or_before(
        cash_operations_df, XtbCashOperationsFile.TIME, valuation_date
    )
    closed_positions_df = _filter_closed_on_or_before(closed_positions_df, valuation_date)

    raw_events, type_warnings = build_xtb_cashflows(cash_operations_df, broker_id)
    warnings.extend(type_warnings)
    events_by_asset, cycle_warnings = partition_broker_cashflows(raw_events)
    warnings.extend(cycle_warnings)
    terminal_by_ticker = _terminal_by_instrument(open_latest)
    qty_by_ticker = _qty_by_instrument(open_latest)
    all_tickers = (
        set(broker_code_from_instrument_id(asset_id) for asset_id in events_by_asset)
        | set(terminal_by_ticker)
        | set(_closed_instruments(closed_positions_df))
    )
    mapping = instruments if instruments is not None else load_instrument_map()
    mapping.require_xtb(all_tickers)

    rows = summarize_broker_cycle_roi(
        broker_id=broker_id,
        valuation_date=valuation_date,
        events_by_asset=events_by_asset,
        terminal_by_code=terminal_by_ticker,
        qty_by_code=qty_by_ticker,
        eval_date=eval_date,
        instrument_name=mapping.instrument_for_xtb,
    )
    append_closed_without_cashflows(
        rows,
        broker_id=broker_id,
        valuation_date=valuation_date,
        events_by_asset=events_by_asset,
        closed_codes=_closed_instruments(closed_positions_df),
        terminal_by_code=terminal_by_ticker,
        qty_by_code=qty_by_ticker,
        eval_date=eval_date,
        instrument_name=mapping.instrument_for_xtb,
    )

    if pool_tx is None:
        try:
            pool_tx = load_accounts_pool(REVOLUT_PLN)
        except Exception as exc:  # noqa: BLE001 — soft warning, nie crash
            if _sum_xtb_card_deposits(cash_operations_df, valuation_date) > MONEY_EPS:
                warnings.append(
                    f"Nie udało się wczytać {REVOLUT_PLN} do reconciliacji XTB: {exc}"
                )
            pool_tx = pd.DataFrame()
    warnings.extend(
        reconcile_xtb_card_funding(
            cash_operations_df, pool_tx, valuation_date=valuation_date
        )
    )

    return pd.DataFrame(rows), events_by_asset, warnings


def reconcile_xtb_card_funding(
    cash_operations_df: pd.DataFrame,
    pool_tx: pd.DataFrame,
    *,
    valuation_date: date | None = None,
    tolerance: float = RECONCILE_TOLERANCE_PLN,
) -> list[str]:
    """Soft: Σ Deposit Adyen (XTB) vs |Σ Opis~XTB| na revolut_pln.

    Wpłaty Pekao / inne banki poza zakresem (brak matcha do Revolut).
    """
    deposits = _sum_xtb_card_deposits(cash_operations_df, valuation_date)
    payments = _sum_revolut_xtb_payments(pool_tx, valuation_date)
    if abs(deposits) <= MONEY_EPS and abs(payments) <= MONEY_EPS:
        return []
    diff = abs(deposits) - abs(payments)
    if abs(diff) <= tolerance:
        return []
    return [
        f"XTB funding mismatch: Adyen Deposit={deposits:.2f} PLN vs "
        f"|Revolut XTB|={abs(payments):.2f} PLN (diff={diff:.2f} PLN)"
    ]


def _sum_xtb_card_deposits(
    cash_operations_df: pd.DataFrame, valuation_date: date | None
) -> float:
    if cash_operations_df is None or cash_operations_df.empty:
        return 0.0
    df = cash_operations_df
    if valuation_date is not None and XtbCashOperationsFile.TIME in df.columns:
        df = _filter_xtb_rows_on_or_before(df, XtbCashOperationsFile.TIME, valuation_date)
    if df.empty or XtbCashOperationsFile.TYPE not in df.columns:
        return 0.0
    type_ok = df[XtbCashOperationsFile.TYPE].map(classify_xtb_cash_type) == CASH_OP_DEPOSIT
    comment = (
        df[XtbCashOperationsFile.COMMENT].astype(str)
        if XtbCashOperationsFile.COMMENT in df.columns
        else pd.Series("", index=df.index)
    )
    card = comment.str.contains(_XTB_CARD_DEPOSIT_COMMENT, case=False, na=False)
    amounts = pd.to_numeric(df.loc[type_ok & card, XtbCashOperationsFile.AMOUNT], errors="coerce")
    return float(amounts.fillna(0.0).abs().sum())


def _sum_revolut_xtb_payments(
    pool_tx: pd.DataFrame, valuation_date: date | None
) -> float:
    if pool_tx is None or pool_tx.empty:
        return 0.0
    df = pool_tx
    if AccountTx.TITLE not in df.columns or AccountTx.AMOUNT not in df.columns:
        return 0.0
    if valuation_date is not None and AccountTx.TRANSACTION_DATE in df.columns:
        df = filter_excel_rows_on_or_before(df, AccountTx.TRANSACTION_DATE, valuation_date)
    mask = df[AccountTx.TITLE].astype(str).str.contains(
        _REVOLUT_XTB_TITLE, case=False, na=False, regex=True
    )
    return float(pd.to_numeric(df.loc[mask, AccountTx.AMOUNT], errors="coerce").fillna(0.0).sum())


def build_xtb_cashflows(
    cash_operations_df: pd.DataFrame,
    broker_id: str,
) -> tuple[dict[str, pd.DataFrame], list[str]]:
    if cash_operations_df is None or cash_operations_df.empty:
        return {}, []

    rows_by_asset: dict[str, list[dict]] = {}
    warnings: list[str] = []
    seen_unknown: set[str] = set()
    for _, row in cash_operations_df.iterrows():
        raw_type = str(row.get(XtbCashOperationsFile.TYPE) or "").strip()
        if is_xtb_cash_footer(raw_type):
            continue
        op_type = classify_xtb_cash_type(raw_type)
        if op_type is None:
            if raw_type and raw_type not in seen_unknown:
                warnings.append(f"Nieznany typ operacji XTB: {raw_type!r}")
                seen_unknown.add(raw_type)
            continue
        if op_type not in TICKER_ROI_TYPES:
            continue
        instrument = xtb_instrument_id(row)
        if not instrument:
            continue
        amount = pd.to_numeric(pd.Series([row.get(XtbCashOperationsFile.AMOUNT)]), errors="coerce").iloc[0]
        if pd.isna(amount):
            continue
        amount = float(amount)
        if op_type == CASH_OP_PURCHASE:
            category = CAPEX
            amount = -abs(amount)
        elif op_type == CASH_OP_SALE:
            category = DIVESTMENT
            amount = abs(amount)
        else:
            category = REVENUES
            amount = abs(amount)

        asset_id = ticker_asset_id(broker_id, instrument)
        # Cash Operations XTB nie ma Volume — qty opcjonalne (cykle tylko gdy uda się uzupełnić).
        rows_by_asset.setdefault(asset_id, []).append(
            {
                CashFlowEvent.ASSET_ID: asset_id,
                CashFlowEvent.DATE: _date_str(row.get(XtbCashOperationsFile.TIME)),
                CashFlowEvent.AMOUNT: amount,
                CashFlowEvent.QUANTITY: None,
                CashFlowEvent.UNIT_PRICE: None,
                CashFlowEvent.CATEGORY: category,
                CashFlowEvent.SOURCE: broker_id,
                CashFlowEvent.DESCRIPTION: raw_type,
                CashFlowEvent.TITLE: str(row.get(XtbCashOperationsFile.INSTRUMENT) or instrument),
                CashFlowEvent.COUNTERPARTY: "",
                CashFlowEvent.ACCOUNT_NUMBER: str(
                    row.get(XtbCashOperationsFile.ID) or row.get(XtbCashOperationsFile.POSITION_ID) or ""
                ),
            }
        )

    result: dict[str, pd.DataFrame] = {}
    for asset_id, rows in rows_by_asset.items():
        df = pd.DataFrame(rows, columns=list(CashFlowEvent.COLUMN_ORDER))
        CashFlowEvent.check_structure(df)
        result[asset_id] = df
    return result, warnings


def _terminal_by_instrument(open_positions_df: pd.DataFrame) -> dict[str, float]:
    result: dict[str, float] = {}
    rows = xtb_open_position_rows(open_positions_df)
    if rows.empty or XtbOpenPositionsFile.VALUE not in rows.columns:
        return result
    for _, row in rows.iterrows():
        instrument = xtb_instrument_id(row)
        if not instrument:
            continue
        value = pd.to_numeric(pd.Series([row.get(XtbOpenPositionsFile.VALUE)]), errors="coerce").iloc[0]
        if pd.notna(value):
            result[instrument] = result.get(instrument, 0.0) + float(value)
    return result


def _qty_by_instrument(open_positions_df: pd.DataFrame) -> dict[str, float]:
    result: dict[str, float] = {}
    rows = xtb_open_position_rows(open_positions_df)
    if rows.empty or XtbOpenPositionsFile.VOLUME not in rows.columns:
        return result
    for _, row in rows.iterrows():
        instrument = xtb_instrument_id(row)
        if not instrument:
            continue
        qty = pd.to_numeric(pd.Series([row.get(XtbOpenPositionsFile.VOLUME)]), errors="coerce").iloc[0]
        if pd.notna(qty):
            result[instrument] = result.get(instrument, 0.0) + float(qty)
    return result


def _closed_instruments(closed_df: pd.DataFrame) -> set[str]:
    if closed_df is None or closed_df.empty:
        return set()
    result = set()
    for _, row in closed_df.iterrows():
        instrument = xtb_instrument_id(row)
        if instrument:
            result.add(instrument)
    return result


def _filter_xtb_rows_on_or_before(df: pd.DataFrame, col: str, valuation_date: date) -> pd.DataFrame:
    if df is None or df.empty or col not in df.columns:
        return df.copy() if df is not None else pd.DataFrame()
    work = df.copy()
    work["_iso_date"] = work[col].map(_date_str)
    filtered = filter_excel_rows_on_or_before(work, "_iso_date", valuation_date)
    return filtered.drop(columns=["_iso_date"])


def _filter_closed_on_or_before(df: pd.DataFrame, valuation_date: date) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if df is not None else pd.DataFrame()
    date_col = XtbClosedPositionsFile.CLOSE_TIME
    if date_col not in df.columns or df[date_col].astype(str).str.strip().eq("").all():
        date_col = XtbClosedPositionsFile.PERIOD_END
    return _filter_xtb_rows_on_or_before(df, date_col, valuation_date)


def _date_str(value) -> str:
    parsed = parse_xtb_date(value)
    if parsed is None:
        return date.today().isoformat()
    return parsed.isoformat()


def _asset_dir(broker_id: str) -> Path:
    return require_broker_asset_dir(broker_id)


def _empty_events() -> pd.DataFrame:
    return empty_cashflow_events()


def _instrument_from_asset_id(asset_id: str) -> str:
    return broker_code_from_instrument_id(asset_id)
