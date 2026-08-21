# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from app_proc.data_root import resolve_asset_dir
from evaluators.valuation_date import filter_excel_rows_on_or_before
from importers.assets.data_model import AssetsDef
from importers.assets.read_assets import read_assets
from importers.degiro.data_model import (
    DEFAULT_DEGIRO_ASSET_ID,
    DegiroAccountFile,
    DegiroPortfolioFile,
    DegiroTransactionsFile,
)
from importers.degiro.read_degiro import (
    latest_portfolio_as_of,
    parse_degiro_date,
    read_degiro_account,
    read_degiro_portfolio,
    read_degiro_transactions,
)
from roi.broker_trading_roi import compute_ticker_roi, ticker_asset_id
from roi.categories import CAPEX, DIVESTMENT, REVENUES
from roi.compute_roi import roi_summary_to_row
from roi.data_model import CashFlowEvent


def build_degiro_cashflows(
    transactions_df: pd.DataFrame,
    account_df: pd.DataFrame,
    broker_id: str,
) -> dict[str, pd.DataFrame]:
    rows_by_asset: dict[str, list[dict]] = {}
    _add_transaction_cashflows(rows_by_asset, transactions_df, broker_id)
    _add_dividend_cashflows(rows_by_asset, account_df, broker_id)

    result: dict[str, pd.DataFrame] = {}
    for asset_id, rows in rows_by_asset.items():
        df = pd.DataFrame(rows, columns=list(CashFlowEvent.COLUMN_ORDER))
        CashFlowEvent.check_structure(df)
        result[asset_id] = df
    return result


def compute_degiro_ticker_roi(
    valuation_date: date,
    *,
    broker_id: str = DEFAULT_DEGIRO_ASSET_ID,
    portfolio_df: pd.DataFrame | None = None,
    transactions_df: pd.DataFrame | None = None,
    account_df: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], list[str]]:
    warnings: list[str] = []
    if portfolio_df is None or transactions_df is None or account_df is None:
        asset_dir = _asset_dir(broker_id)
        if portfolio_df is None:
            portfolio_df = read_degiro_portfolio(asset_dir, broker_id)
        if transactions_df is None:
            transactions_df, tx_warnings = read_degiro_transactions(asset_dir, broker_id)
            warnings.extend(tx_warnings)
        if account_df is None:
            account_df, account_warnings = read_degiro_account(asset_dir, broker_id)
            warnings.extend(account_warnings)

    portfolio = latest_portfolio_as_of(portfolio_df, valuation_date)
    tx = _filter_degiro_rows_on_or_before(transactions_df, DegiroTransactionsFile.DATE, valuation_date)
    account = _filter_degiro_rows_on_or_before(account_df, DegiroAccountFile.BOOKING_DATE, valuation_date)

    events_by_asset = build_degiro_cashflows(tx, account, broker_id)
    terminal_by_isin = _terminal_by_isin(portfolio)
    qty_by_isin = _qty_by_isin(portfolio)
    all_isins = set(_isin_from_asset_id(a) for a in events_by_asset) | set(terminal_by_isin)

    rows = []
    for isin in sorted(i for i in all_isins if i):
        asset_id = ticker_asset_id(broker_id, isin)
        events = events_by_asset.get(asset_id, _empty_events())
        terminal = float(terminal_by_isin.get(isin, 0.0))
        qty = float(qty_by_isin.get(isin, 0.0))
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


def _add_transaction_cashflows(
    rows_by_asset: dict[str, list[dict]],
    transactions_df: pd.DataFrame,
    broker_id: str,
) -> None:
    if transactions_df is None or transactions_df.empty:
        return
    for _, row in transactions_df.iterrows():
        isin = str(row.get(DegiroTransactionsFile.ISIN) or "").strip()
        if not isin:
            continue
        amount = row.get(DegiroTransactionsFile.VALUE_EUR)
        if pd.isna(amount):
            continue
        amount = float(amount)
        qty = row.get(DegiroTransactionsFile.QUANTITY)
        qty = float(qty) if pd.notna(qty) else 0.0
        if amount < 0 or qty > 0:
            category = CAPEX
            amount = -abs(amount)
        else:
            category = DIVESTMENT
            amount = abs(amount)
        asset_id = ticker_asset_id(broker_id, isin)
        rows_by_asset.setdefault(asset_id, []).append(
            _event_row(
                asset_id=asset_id,
                date_value=row.get(DegiroTransactionsFile.DATE),
                amount=amount,
                category=category,
                source=broker_id,
                description="BUY" if category == CAPEX else "SELL",
                title=str(row.get(DegiroTransactionsFile.PRODUCT) or isin),
                account_number=str(row.get(DegiroTransactionsFile.ORDER_ID) or ""),
            )
        )


def _add_dividend_cashflows(
    rows_by_asset: dict[str, list[dict]],
    account_df: pd.DataFrame,
    broker_id: str,
) -> None:
    if account_df is None or account_df.empty:
        return
    desc = account_df[DegiroAccountFile.DESCRIPTION].astype(str)
    dividends = account_df.loc[desc.str.contains(DegiroAccountFile.DESCRIPTION_DIVIDEND, case=False, na=False)]
    for _, row in dividends.iterrows():
        isin = str(row.get(DegiroAccountFile.ISIN) or "").strip()
        if not isin:
            continue
        amount = row.get(DegiroAccountFile.CHANGE)
        if pd.isna(amount):
            continue
        asset_id = ticker_asset_id(broker_id, isin)
        rows_by_asset.setdefault(asset_id, []).append(
            _event_row(
                asset_id=asset_id,
                date_value=row.get(DegiroAccountFile.BOOKING_DATE),
                amount=abs(float(amount)),
                category=REVENUES,
                source=broker_id,
                description=str(row.get(DegiroAccountFile.DESCRIPTION) or ""),
                title=str(row.get(DegiroAccountFile.PRODUCT) or isin),
                account_number=str(row.get(DegiroAccountFile.ORDER_ID) or ""),
            )
        )


def _event_row(
    *,
    asset_id: str,
    date_value,
    amount: float,
    category: str,
    source: str,
    description: str,
    title: str,
    account_number: str,
) -> dict[str, object]:
    return {
        CashFlowEvent.ASSET_ID: asset_id,
        CashFlowEvent.DATE: parse_degiro_date(date_value).isoformat(),
        CashFlowEvent.AMOUNT: float(amount),
        CashFlowEvent.CATEGORY: category,
        CashFlowEvent.SOURCE: source,
        CashFlowEvent.DESCRIPTION: description,
        CashFlowEvent.TITLE: title,
        CashFlowEvent.COUNTERPARTY: "",
        CashFlowEvent.ACCOUNT_NUMBER: account_number,
    }


def _terminal_by_isin(portfolio_df: pd.DataFrame) -> dict[str, float]:
    if portfolio_df is None or portfolio_df.empty:
        return {}
    result: dict[str, float] = {}
    positions = portfolio_df[_has_isin(portfolio_df, DegiroPortfolioFile.ISIN)]
    for _, row in positions.iterrows():
        isin = str(row[DegiroPortfolioFile.ISIN]).strip()
        result[isin] = result.get(isin, 0.0) + float(row.get(DegiroPortfolioFile.VALUE_EUR) or 0.0)
    return result


def _qty_by_isin(portfolio_df: pd.DataFrame) -> dict[str, float]:
    if portfolio_df is None or portfolio_df.empty:
        return {}
    result: dict[str, float] = {}
    positions = portfolio_df[_has_isin(portfolio_df, DegiroPortfolioFile.ISIN)]
    for _, row in positions.iterrows():
        isin = str(row[DegiroPortfolioFile.ISIN]).strip()
        result[isin] = result.get(isin, 0.0) + float(row.get(DegiroPortfolioFile.QUANTITY) or 0.0)
    return result


def _filter_degiro_rows_on_or_before(df: pd.DataFrame, col: str, valuation_date: date) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if df is not None else pd.DataFrame()
    work = df.copy()
    work["_iso_date"] = work[col].map(lambda v: parse_degiro_date(v).isoformat())
    filtered = filter_excel_rows_on_or_before(work, "_iso_date", valuation_date)
    return filtered.drop(columns=["_iso_date"])


def _has_isin(df: pd.DataFrame, col: str) -> pd.Series:
    return df[col].notna() & df[col].astype(str).str.strip().ne("")


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


def _isin_from_asset_id(asset_id: str) -> str:
    return str(asset_id).split(":", 1)[-1]
