# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from app_proc.data_root import resolve_asset_dir
from evaluators.valuation_date import filter_excel_rows_on_or_before
from importers.assets.data_model import AssetsDef
from importers.assets.read_assets import read_assets
from importers.xtb.data_model import DEFAULT_XTB_ASSET_ID
from importers.xtb.read_xtb import (
    latest_xtb_report_as_of,
    read_xtb_cash_operations,
    read_xtb_open_positions,
    xtb_open_position_rows,
)
from roi.broker_trading_roi import compute_ticker_roi, ticker_asset_id
from roi.categories import CAPEX, DIVESTMENT, OPEX, REVENUES
from roi.compute_roi import roi_summary_to_row
from roi.data_model import CashFlowEvent


def compute_xtb_ticker_roi(
    valuation_date: date,
    *,
    broker_id: str = DEFAULT_XTB_ASSET_ID,
    cash_operations_df: pd.DataFrame | None = None,
    open_positions_df: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], list[str]]:
    warnings: list[str] = []
    if cash_operations_df is None or open_positions_df is None:
        asset_dir = _asset_dir(broker_id)
        report = latest_xtb_report_as_of(asset_dir, valuation_date, required_kind="open")
        if report is None:
            return pd.DataFrame(), {}, [f"Brak raportu XTB <= {valuation_date.isoformat()} dla {broker_id}."]
        if cash_operations_df is None:
            cash_operations_df = read_xtb_cash_operations(report)
        if open_positions_df is None:
            open_positions_df = read_xtb_open_positions(report)

    cash_operations_df = _filter_xtb_rows_on_or_before(cash_operations_df, "Time", valuation_date)
    events_by_asset = build_xtb_cashflows(cash_operations_df, broker_id)
    terminal_by_ticker = _terminal_by_ticker(open_positions_df)
    qty_by_ticker = _qty_by_ticker(open_positions_df)
    all_tickers = set(_ticker_from_asset_id(asset_id) for asset_id in events_by_asset) | set(terminal_by_ticker)

    rows = []
    for ticker in sorted(t for t in all_tickers if t):
        asset_id = ticker_asset_id(broker_id, ticker)
        events = events_by_asset.get(asset_id, _empty_events())
        terminal = float(terminal_by_ticker.get(ticker, 0.0))
        qty = float(qty_by_ticker.get(ticker, 0.0))
        open_qty = 1.0 if abs(qty) > 1e-12 and terminal != 0.0 else 0.0
        summary = compute_ticker_roi(
            asset_id,
            events,
            valuation_date,
            open_qty=open_qty,
            last_price=terminal if open_qty else 0.0,
        )
        rows.append(roi_summary_to_row(summary))

    return pd.DataFrame(rows), events_by_asset, warnings


def build_xtb_cashflows(cash_operations_df: pd.DataFrame, broker_id: str) -> dict[str, pd.DataFrame]:
    if cash_operations_df is None or cash_operations_df.empty:
        return {}

    rows_by_asset: dict[str, list[dict]] = {}
    for _, row in cash_operations_df.iterrows():
        ticker = str(row.get("Ticker") or "").strip()
        if not ticker:
            continue
        category = _roi_category(str(row.get("Type") or ""))
        if category is None:
            continue
        amount = pd.to_numeric(pd.Series([row.get("Amount")]), errors="coerce").iloc[0]
        if pd.isna(amount):
            continue
        amount = float(amount)
        if category == CAPEX:
            amount = -abs(amount)
        elif category in (DIVESTMENT, REVENUES):
            amount = abs(amount)
        elif category == OPEX:
            amount = -abs(amount)

        asset_id = ticker_asset_id(broker_id, ticker)
        rows_by_asset.setdefault(asset_id, []).append(
            {
                CashFlowEvent.ASSET_ID: asset_id,
                CashFlowEvent.DATE: _date_str(row.get("Time")),
                CashFlowEvent.AMOUNT: amount,
                CashFlowEvent.CATEGORY: category,
                CashFlowEvent.SOURCE: broker_id,
                CashFlowEvent.DESCRIPTION: str(row.get("Type") or ""),
                CashFlowEvent.TITLE: str(row.get("Instrument") or ticker),
                CashFlowEvent.COUNTERPARTY: "",
                CashFlowEvent.ACCOUNT_NUMBER: str(row.get("ID") or row.get("Position ID") or ""),
            }
        )

    result: dict[str, pd.DataFrame] = {}
    for asset_id, rows in rows_by_asset.items():
        df = pd.DataFrame(rows, columns=list(CashFlowEvent.COLUMN_ORDER))
        CashFlowEvent.check_structure(df)
        result[asset_id] = df
    return result


def _roi_category(operation_type: str) -> str | None:
    text = operation_type.strip().lower()
    if "purchase" in text or "buy" in text:
        return CAPEX
    if "sale" in text or "sell" in text:
        return DIVESTMENT
    if "dividend" in text:
        return REVENUES
    if "commission" in text or "fee" in text or "tax" in text:
        return OPEX
    return None


def _terminal_by_ticker(open_positions_df: pd.DataFrame) -> dict[str, float]:
    result: dict[str, float] = {}
    rows = xtb_open_position_rows(open_positions_df)
    if rows.empty or "Ticker" not in rows.columns or "Value" not in rows.columns:
        return result
    for _, row in rows.iterrows():
        ticker = str(row.get("Ticker") or "").strip()
        if not ticker:
            continue
        value = pd.to_numeric(pd.Series([row.get("Value")]), errors="coerce").iloc[0]
        if pd.notna(value):
            result[ticker] = result.get(ticker, 0.0) + float(value)
    return result


def _qty_by_ticker(open_positions_df: pd.DataFrame) -> dict[str, float]:
    result: dict[str, float] = {}
    rows = xtb_open_position_rows(open_positions_df)
    if rows.empty or "Ticker" not in rows.columns or "Volume" not in rows.columns:
        return result
    for _, row in rows.iterrows():
        ticker = str(row.get("Ticker") or "").strip()
        if not ticker:
            continue
        qty = pd.to_numeric(pd.Series([row.get("Volume")]), errors="coerce").iloc[0]
        if pd.notna(qty):
            result[ticker] = result.get(ticker, 0.0) + float(qty)
    return result


def _filter_xtb_rows_on_or_before(df: pd.DataFrame, col: str, valuation_date: date) -> pd.DataFrame:
    if df is None or df.empty or col not in df.columns:
        return df.copy() if df is not None else pd.DataFrame()
    work = df.copy()
    work["_iso_date"] = work[col].map(_date_str)
    filtered = filter_excel_rows_on_or_before(work, "_iso_date", valuation_date)
    return filtered.drop(columns=["_iso_date"])


def _date_str(value) -> str:
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return date.today().isoformat()
    return ts.date().isoformat()


def _asset_dir(broker_id: str) -> Path:
    assets = read_assets()
    rows = assets[assets[AssetsDef.ID].astype(str) == broker_id]
    if rows.empty:
        raise ValueError(f"Brak aktywa brokerskiego {broker_id!r} w a_config.xlsx (arkusz assets)")
    row = rows.iloc[0]
    asset_dir = resolve_asset_dir(broker_id, row[AssetsDef.TYPE])
    if not Path(asset_dir).is_dir():
        raise ValueError(f"Brak katalogu brokera: {asset_dir}")
    return asset_dir


def _empty_events() -> pd.DataFrame:
    return pd.DataFrame(columns=list(CashFlowEvent.COLUMN_ORDER))


def _ticker_from_asset_id(asset_id: str) -> str:
    return str(asset_id).split(":", 1)[-1]
