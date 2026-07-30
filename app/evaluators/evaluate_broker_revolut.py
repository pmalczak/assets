# -*- coding: utf-8 -*-
from __future__ import annotations

__author__ = "pmalczak@gmail.com"

import re
from datetime import date
from pathlib import Path

import pandas as pd

from app_proc.data_root import resolve_asset_dir
from evaluators.valuation_date import format_date_columns
from importers.assets.data_model import AssetsDef, GroupDomain, TypeDomain
from importers.revolut.read_r_trading import (
    isin_by_symbol,
    read_revolut_trading_pnl,
    read_revolut_trading_transactions,
)
from importers.revolut.trading_data_model import RevolutTradingFile


def evaluate_broker_revolut(
    data_root: Path,
    asset_id: str,
    assets_file_row: pd.Series,
    valuation_date: date,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Wycena otwartych pozycji brokerskich Revolut kosztem nabycia (FIFO).
    """
    p = resolve_asset_dir(asset_id, assets_file_row[AssetsDef.TYPE])
    if not p.is_dir():
        raise ValueError(p)

    warnings: list[str] = []
    trading_df, trading_warnings = read_revolut_trading_transactions(p, asset_id)
    warnings.extend(trading_warnings)
    pnl_df, pnl_warnings = read_revolut_trading_pnl(p, asset_id)
    warnings.extend(pnl_warnings)

    RevolutTradingFile.check_structure(trading_df)
    trading_df = filter_trading_on_or_before(trading_df, valuation_date)
    if trading_df.empty:
        return pd.DataFrame(columns=list(AssetsDef.expected_columns())), warnings

    isin_map = isin_by_symbol(pnl_df)
    holdings = open_holdings_at_cost(trading_df)
    if not holdings:
        return pd.DataFrame(columns=list(AssetsDef.expected_columns())), warnings

    data = []
    for ticker, info in sorted(holdings.items()):
        row = AssetsDef.as_assets_row(assets_file_row)
        row[AssetsDef.VALUE] = info["cost"]
        row[AssetsDef.EVALUATION_DATE] = info["eval_date"]
        row[AssetsDef.TYPE] = TypeDomain.EQUITIES
        row[AssetsDef.GROUP] = GroupDomain.INVESTMENT
        isin = isin_map.get(ticker)
        row[AssetsDef.DESCR] = f"{ticker} {isin}" if isin else ticker
        if AssetsDef.CURRENCY in row.index and info.get("currency"):
            row[AssetsDef.CURRENCY] = info["currency"]
        data.append(row)

    result = pd.DataFrame(data=data)
    AssetsDef.check_structure(result)
    return format_date_columns(result, AssetsDef.EVALUATION_DATE), warnings


def filter_trading_on_or_before(df: pd.DataFrame, valuation_date: date) -> pd.DataFrame:
    """Filtr daty dla ISO8601 UTC z blottera trading (filter_on_or_before jest tz-naive)."""
    if df.empty:
        return df.copy()
    parsed = pd.to_datetime(df[RevolutTradingFile.DATE], format="ISO8601", utc=True).dt.normalize()
    cutoff = pd.Timestamp(valuation_date, tz="UTC").normalize()
    return df.loc[parsed <= cutoff].copy()


def open_holdings_at_cost(trading_df: pd.DataFrame) -> dict[str, dict]:
    """
    FIFO: otwarte loty → wartość = Σ qty_pozostała × cena_zakupu.
    Zwraca {ticker: {qty, cost, eval_date, currency}}.
    """
    work = trading_df.copy()
    work["_dt"] = pd.to_datetime(work[RevolutTradingFile.DATE], format="ISO8601", utc=True)
    work = work.sort_values("_dt")

    lots: dict[str, list[dict]] = {}
    currency_by_ticker: dict[str, str] = {}

    for _, row in work.iterrows():
        tx_type = row[RevolutTradingFile.TYPE]
        ticker = row[RevolutTradingFile.TICKER]
        if pd.isna(ticker) or not str(ticker).strip():
            continue
        ticker = str(ticker).strip()
        ccy = str(row[RevolutTradingFile.CURRENCY] or "").strip() or None
        if ccy:
            currency_by_ticker[ticker] = ccy

        if tx_type == RevolutTradingFile.TYPE_BUY:
            qty = _to_float(row[RevolutTradingFile.QUANTITY])
            price = parse_trading_number(row[RevolutTradingFile.PRICE_PER_SHARE])
            if qty is None or price is None or qty <= 0:
                continue
            lots.setdefault(ticker, []).append(
                {"qty": qty, "price": price, "date": row["_dt"]}
            )
        elif tx_type == RevolutTradingFile.TYPE_SELL:
            qty = _to_float(row[RevolutTradingFile.QUANTITY])
            if qty is None or qty == 0:
                continue
            # Po normalize_trading_transactions Quantity SELL jest ujemne.
            remaining = abs(qty)
            open_lots = lots.setdefault(ticker, [])
            while remaining > 1e-12 and open_lots:
                lot = open_lots[0]
                take = min(lot["qty"], remaining)
                lot["qty"] -= take
                remaining -= take
                if lot["qty"] <= 1e-12:
                    open_lots.pop(0)
            if remaining > 1e-6:
                raise ValueError(
                    f"SELL {ticker}: brak lotów FIFO (niedobór qty={remaining})"
                )

    result = {}
    for ticker, open_lots in lots.items():
        qty = sum(lot["qty"] for lot in open_lots)
        if qty <= 1e-12:
            continue
        cost = sum(lot["qty"] * lot["price"] for lot in open_lots)
        last_dt = max(lot["date"] for lot in open_lots)
        eval_date = last_dt.tz_convert(None).date().isoformat() if last_dt.tzinfo else last_dt.date().isoformat()
        result[ticker] = {
            "qty": qty,
            "cost": float(cost),
            "eval_date": eval_date,
            "currency": currency_by_ticker.get(ticker),
        }
    return result


def parse_trading_number(value) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    s = s.replace(",", "")
    s = re.sub(r"[^\d.\-]", "", s)
    if s in ("", "-", ".", "-."):
        return None
    return float(s)


def _to_float(value) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return parse_trading_number(value)
