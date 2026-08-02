# -*- coding: utf-8 -*-
"""ROI per ticker z blottera Revolut robo + reconciliacja CASH TOP-UP vs ROR."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from analyse_assets.account_tx import AccountTx
from analyse_assets.accounts_pools import load_accounts_pool
from app_proc.data_root import resolve_asset_dir
from evaluators.evaluate_broker_revolut import (
    filter_trading_on_or_before,
    open_holdings_at_cost,
    parse_trading_number,
)
from evaluators.valuation_date import filter_excel_rows_on_or_before
from importers.assets.data_model import AssetsDef, KindDomain
from importers.assets.pool_id import REVOLUT_EUR
from importers.assets.read_assets import read_assets
from importers.revolut.read_r_trading import read_revolut_trading_transactions
from importers.revolut.trading_data_model import RevolutTradingFile
from roi.categories import INFLOW, INVESTMENT
from roi.compute_roi import RoiSummary, _aggregate_category, roi_summary_to_row
from roi.data_model import CashFlowEvent
from roi.xirr import cashflows_for_xirr, compute_xirr

TO_ROBO_TITLE = "To Robo portfolio"
DEFAULT_BROKER_ASSET_ID = "p_re_robo"
RECONCILE_TOLERANCE_EUR = 0.01


def ticker_asset_id(broker_id: str, ticker: str) -> str:
    return f"{broker_id}:{str(ticker).strip()}"


def build_broker_ticker_cashflows(
    trading_df: pd.DataFrame,
    broker_id: str,
) -> dict[str, pd.DataFrame]:
    """BUY→INVESTMENT, SELL/DIV→INFLOW. FEE/TOP-UP poza ROI ticker."""
    empty_cols = list(CashFlowEvent.COLUMN_ORDER)
    if trading_df is None or trading_df.empty:
        return {}

    by_ticker: dict[str, list[dict]] = {}
    for _, row in trading_df.iterrows():
        tx_type = row[RevolutTradingFile.TYPE]
        ticker = row.get(RevolutTradingFile.TICKER)
        if pd.isna(ticker) or not str(ticker).strip():
            continue
        ticker = str(ticker).strip()
        amount = parse_trading_number(row[RevolutTradingFile.TOTAL_AMOUNT])
        if amount is None:
            continue
        event_date = _trading_date_str(row[RevolutTradingFile.DATE])
        if event_date is None:
            continue

        if tx_type == RevolutTradingFile.TYPE_BUY:
            category = INVESTMENT
            # Po normalize Total Amount BUY jest ujemne; wymuś znak INVESTMENT.
            amount = -abs(amount)
        elif tx_type in (RevolutTradingFile.TYPE_SELL, RevolutTradingFile.TYPE_DIVIDEND):
            category = INFLOW
            amount = abs(amount)
        else:
            continue

        asset_id = ticker_asset_id(broker_id, ticker)
        by_ticker.setdefault(ticker, []).append(
            {
                CashFlowEvent.ASSET_ID: asset_id,
                CashFlowEvent.DATE: event_date,
                CashFlowEvent.AMOUNT: float(amount),
                CashFlowEvent.CATEGORY: category,
                CashFlowEvent.SOURCE: broker_id,
                CashFlowEvent.DESCRIPTION: str(tx_type),
                CashFlowEvent.TITLE: ticker,
                CashFlowEvent.COUNTERPARTY: "",
                CashFlowEvent.ACCOUNT_NUMBER: "",
            }
        )

    result: dict[str, pd.DataFrame] = {}
    for ticker, rows in by_ticker.items():
        df = pd.DataFrame(rows, columns=empty_cols)
        CashFlowEvent.check_structure(df)
        result[ticker_asset_id(broker_id, ticker)] = df
    return result


def ticker_open_state(trading_df: pd.DataFrame) -> dict[str, dict]:
    """
    Stan otwarcia per ticker: qty (FIFO), last_price (ostatnia cena BUY/SELL).
    Tickery z historią ale qty=0: last_price z ostatniej transakcji (0 jeśli brak).
    """
    if trading_df is None or trading_df.empty:
        return {}

    holdings = open_holdings_at_cost(trading_df)
    last_prices = _last_trade_prices(trading_df)
    tickers = set(holdings) | set(last_prices) | set(_tickers_with_roi_events(trading_df))

    state: dict[str, dict] = {}
    for ticker in tickers:
        info = holdings.get(ticker, {})
        qty = float(info.get("qty") or 0.0)
        state[ticker] = {
            "qty": qty,
            "last_price": float(last_prices.get(ticker) or 0.0),
            "cost": float(info.get("cost") or 0.0),
        }
    return state


def compute_ticker_roi(
    asset_id: str,
    cashflows: pd.DataFrame,
    valuation_date: date,
    *,
    open_qty: float,
    last_price: float,
) -> RoiSummary:
    """ROI jak compute_roi, ale terminal = last_price×qty; is_sold ⇔ qty≈0 (bez CLOSING)."""
    filtered = filter_excel_rows_on_or_before(cashflows, CashFlowEvent.DATE, valuation_date)

    capex = _aggregate_category(filtered, INVESTMENT)
    opex = 0.0
    revenue = _aggregate_category(filtered, INFLOW)
    sold = abs(open_qty) <= 1e-12
    terminal_realized = 0.0
    terminal_unrealized = 0.0 if sold else float(last_price) * float(open_qty)

    flows_total = float(filtered[CashFlowEvent.AMOUNT].sum()) if not filtered.empty else 0.0
    roi_nominal = flows_total + terminal_unrealized

    xirr_dates, xirr_amounts = cashflows_for_xirr(filtered, valuation_date, terminal_unrealized)
    xirr = compute_xirr(xirr_dates, xirr_amounts)

    return RoiSummary(
        asset_id=asset_id,
        capex=capex,
        opex=opex,
        revenue=revenue,
        terminal_realized=terminal_realized,
        terminal_unrealized=terminal_unrealized,
        roi_nominal=roi_nominal,
        xirr=xirr,
        is_sold=sold,
        warnings=[],
    )


def reconcile_robo_top_up(
    trading_df: pd.DataFrame,
    pool_tx: pd.DataFrame,
    *,
    valuation_date: date | None = None,
    tolerance: float = RECONCILE_TOLERANCE_EUR,
) -> list[str]:
    """Σ CASH TOP-UP (trading) vs abs(Σ To Robo portfolio) z revolut_eur."""
    top_up = _sum_cash_top_up(trading_df, valuation_date)
    to_robo = _sum_to_robo(pool_tx, valuation_date)
    diff = abs(top_up) - abs(to_robo)
    if abs(diff) <= tolerance:
        return []
    return [
        f"Robo funding mismatch: CASH TOP-UP={top_up:.2f} EUR vs "
        f"|To Robo|={abs(to_robo):.2f} EUR (diff={diff:.2f} EUR)"
    ]


def compute_broker_ticker_roi_from_trading(
    trading_df: pd.DataFrame,
    valuation_date: date,
    broker_id: str = DEFAULT_BROKER_ASSET_ID,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    filtered = filter_trading_on_or_before(trading_df, valuation_date)
    events_by_asset = build_broker_ticker_cashflows(filtered, broker_id)
    state = ticker_open_state(filtered)

    rows = []
    for asset_id, events in sorted(events_by_asset.items()):
        ticker = asset_id.split(":", 1)[-1]
        st = state.get(ticker, {"qty": 0.0, "last_price": 0.0})
        summary = compute_ticker_roi(
            asset_id,
            events,
            valuation_date,
            open_qty=st["qty"],
            last_price=st["last_price"],
        )
        rows.append(roi_summary_to_row(summary))

    summary_df = pd.DataFrame(rows)
    return summary_df, events_by_asset


def compute_revolut_robo_ticker_roi(
    valuation_date: date,
    *,
    broker_id: str = DEFAULT_BROKER_ASSET_ID,
    trading_df: pd.DataFrame | None = None,
    pool_tx: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], list[str]]:
    """
    API: ROI per ticker + ostrzeżenia (w tym reconciliacja TOP-UP vs To Robo).
    trading_df / pool_tx opcjonalne (testy); domyślnie z dysku / pool.
    """
    warnings: list[str] = []
    if trading_df is None:
        trading_df, load_warnings = _load_broker_trading(broker_id)
        warnings.extend(load_warnings)

    summary, events = compute_broker_ticker_roi_from_trading(
        trading_df, valuation_date, broker_id
    )

    if pool_tx is None:
        try:
            pool_tx = load_accounts_pool(REVOLUT_EUR)
        except Exception as exc:  # noqa: BLE001 — UI/raport: warning zamiast crash
            warnings.append(f"Nie udało się wczytać {REVOLUT_EUR} do reconciliacji: {exc}")
            pool_tx = pd.DataFrame()

    filtered_trading = filter_trading_on_or_before(trading_df, valuation_date)
    warnings.extend(
        reconcile_robo_top_up(filtered_trading, pool_tx, valuation_date=valuation_date)
    )
    return summary, events, warnings


def _load_broker_trading(broker_id: str) -> tuple[pd.DataFrame, list[str]]:
    assets = read_assets()
    rows = assets[assets[AssetsDef.ID].astype(str) == broker_id]
    if rows.empty:
        # Fallback: pierwszy BROKER w katalogu o tym id-prefiksie
        broker_mask = assets[AssetsDef.KIND].astype(str).str.startswith(KindDomain.BROKER)
        rows = assets.loc[broker_mask & (assets[AssetsDef.ID].astype(str) == broker_id)]
    if rows.empty:
        raise ValueError(f"Brak aktywa brokerskiego {broker_id!r} w a_config.xlsx (arkusz assets)")
    row = rows.iloc[0]
    asset_dir = resolve_asset_dir(broker_id, row[AssetsDef.TYPE])
    if not Path(asset_dir).is_dir():
        raise ValueError(f"Brak katalogu brokera: {asset_dir}")
    return read_revolut_trading_transactions(asset_dir, broker_id)


def _trading_date_str(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    ts = pd.to_datetime(value, format="ISO8601", utc=True, errors="coerce")
    if pd.isna(ts):
        ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return None
    if getattr(ts, "tzinfo", None) is not None:
        ts = ts.tz_convert(None)
    return ts.date().isoformat()


def _last_trade_prices(trading_df: pd.DataFrame) -> dict[str, float]:
    work = trading_df.copy()
    work["_dt"] = pd.to_datetime(work[RevolutTradingFile.DATE], format="ISO8601", utc=True)
    work = work.sort_values("_dt")
    prices: dict[str, float] = {}
    for _, row in work.iterrows():
        if row[RevolutTradingFile.TYPE] not in (
            RevolutTradingFile.TYPE_BUY,
            RevolutTradingFile.TYPE_SELL,
        ):
            continue
        ticker = row.get(RevolutTradingFile.TICKER)
        if pd.isna(ticker) or not str(ticker).strip():
            continue
        price = parse_trading_number(row[RevolutTradingFile.PRICE_PER_SHARE])
        if price is None:
            continue
        prices[str(ticker).strip()] = float(price)
    return prices


def _tickers_with_roi_events(trading_df: pd.DataFrame) -> set[str]:
    types = {
        RevolutTradingFile.TYPE_BUY,
        RevolutTradingFile.TYPE_SELL,
        RevolutTradingFile.TYPE_DIVIDEND,
    }
    mask = trading_df[RevolutTradingFile.TYPE].isin(types)
    tickers = trading_df.loc[mask, RevolutTradingFile.TICKER].dropna().astype(str).str.strip()
    return {t for t in tickers if t}


def _sum_cash_top_up(trading_df: pd.DataFrame, valuation_date: date | None) -> float:
    if trading_df is None or trading_df.empty:
        return 0.0
    df = trading_df
    if valuation_date is not None:
        df = filter_trading_on_or_before(df, valuation_date)
    mask = df[RevolutTradingFile.TYPE] == RevolutTradingFile.TYPE_CASH_TOP_UP
    total = 0.0
    for value in df.loc[mask, RevolutTradingFile.TOTAL_AMOUNT]:
        amount = parse_trading_number(value)
        if amount is not None:
            total += abs(float(amount))
    return total


def _sum_to_robo(pool_tx: pd.DataFrame, valuation_date: date | None) -> float:
    if pool_tx is None or pool_tx.empty:
        return 0.0
    df = pool_tx
    title_col = AccountTx.TITLE if AccountTx.TITLE in df.columns else None
    amount_col = AccountTx.AMOUNT if AccountTx.AMOUNT in df.columns else None
    if title_col is None or amount_col is None:
        return 0.0
    if valuation_date is not None and AccountTx.TRANSACTION_DATE in df.columns:
        df = filter_excel_rows_on_or_before(df, AccountTx.TRANSACTION_DATE, valuation_date)
    mask = df[title_col].astype(str).str.contains(TO_ROBO_TITLE, case=False, na=False)
    return float(pd.to_numeric(df.loc[mask, amount_col], errors="coerce").fillna(0.0).sum())
