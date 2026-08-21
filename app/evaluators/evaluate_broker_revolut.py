# -*- coding: utf-8 -*-
from __future__ import annotations

__author__ = "pmalczak@gmail.com"

import re
from datetime import date
from pathlib import Path

import pandas as pd

from app_proc.data_root import resolve_asset_dir
from evaluators.broker_snapshot import BrokerHoldings, BrokerSnapshotEvaluator
from importers.assets.data_model import AssetsDef
from importers.revolut.read_r_trading import (
    read_revolut_trading_pnl,
    read_revolut_trading_transactions,
)
from importers.revolut.trading_data_model import (
    DEFAULT_REVOLUT_ROBO_ASSET_ID,
    RevolutTradingFile,
)

_CASH_OUT_ABS = {
    RevolutTradingFile.TYPE_BUY,
    RevolutTradingFile.TYPE_ROBO_FEE,
}
_CASH_IN_ABS = {
    RevolutTradingFile.TYPE_SELL,
}
_CASH_AS_IS = {
    RevolutTradingFile.TYPE_DIVIDEND,
    RevolutTradingFile.TYPE_CASH_TOP_UP,
}
_CASH_TYPES = _CASH_OUT_ABS | _CASH_IN_ABS | _CASH_AS_IS


def is_revolut_robo_broker(assets_file_row: pd.Series) -> bool:
    return str(assets_file_row.get(AssetsDef.ID, "")).strip() == DEFAULT_REVOLUT_ROBO_ASSET_ID


class RevolutRoboSnapshotEvaluator(BrokerSnapshotEvaluator):
    def matches(self, assets_file_row: pd.Series) -> bool:
        return is_revolut_robo_broker(assets_file_row)

    def load_holdings(
        self,
        data_root: Path,
        asset_id: str,
        assets_file_row: pd.Series,
        valuation_date: date,
    ) -> tuple[BrokerHoldings | None, list[str]]:
        p = resolve_asset_dir(asset_id, assets_file_row[AssetsDef.TYPE])
        warnings: list[str] = []
        if not p.is_dir():
            warnings.append(
                f"Brak katalogu {p} — uruchom Import wyciągów "
                f"(trading-account-statement → assets/{asset_id}/)."
            )
            return None, warnings

        trading_df, trading_warnings = read_revolut_trading_transactions(p, asset_id)
        warnings.extend(trading_warnings)
        _pnl_df, pnl_warnings = read_revolut_trading_pnl(p, asset_id)
        warnings.extend(pnl_warnings)

        RevolutTradingFile.check_structure(trading_df)
        trading_df = filter_trading_on_or_before(trading_df, valuation_date)
        if trading_df.empty:
            return None, warnings

        holdings = open_holdings_at_cost(trading_df)
        cash_value, cash_warnings = revolut_working_cash(trading_df)
        warnings.extend(cash_warnings)
        positions_value = sum(info["cost"] for info in holdings.values())
        return (
            BrokerHoldings(
                positions_value=float(positions_value),
                cash_value=float(cash_value),
                n_positions=len(holdings),
                n_cash_rows=1,
                evaluation_date=_evaluation_date(trading_df, holdings, valuation_date),
                currency=_currency(trading_df, holdings),
            ),
            warnings,
        )


def evaluate_broker_revolut(
    data_root: Path,
    asset_id: str,
    assets_file_row: pd.Series,
    valuation_date: date,
) -> tuple[pd.DataFrame, list[str]]:
    """Syntetyczna wycena rachunku Revolut robo: FIFO otwartych pozycji + gotówka z blottera."""
    return RevolutRoboSnapshotEvaluator().evaluate(
        data_root, asset_id, assets_file_row, valuation_date
    )


def revolut_working_cash(trading_df: pd.DataFrame) -> tuple[float, list[str]]:
    """
    Saldo gotówki z blottera po normalizacji znaków:
    BUY/FEE → wypływ (−abs), SELL → wpływ (+abs), TOP-UP/DIVIDEND → kwota jak w pliku.
    """
    if trading_df is None or trading_df.empty:
        return 0.0, []
    cash = 0.0
    unknown: set[str] = set()
    for _, row in trading_df.iterrows():
        tx_type = row[RevolutTradingFile.TYPE]
        amount = parse_trading_number(row[RevolutTradingFile.TOTAL_AMOUNT])
        if amount is None:
            continue
        if tx_type in _CASH_OUT_ABS:
            cash += -abs(amount)
        elif tx_type in _CASH_IN_ABS:
            cash += abs(amount)
        elif tx_type in _CASH_AS_IS:
            cash += amount
        else:
            unknown.add(str(tx_type))
    warnings = [
        f"Revolut robo: nieznany Type {tx_type!r} poza saldem gotówki"
        for tx_type in sorted(unknown)
    ]
    return float(cash), warnings


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
        eval_date = (
            last_dt.tz_convert(None).date().isoformat()
            if last_dt.tzinfo
            else last_dt.date().isoformat()
        )
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


def _evaluation_date(
    trading_df: pd.DataFrame,
    holdings: dict[str, dict],
    valuation_date: date,
) -> str:
    eval_dates = [info["eval_date"] for info in holdings.values() if info.get("eval_date")]
    if eval_dates:
        return max(eval_dates)
    parsed = pd.to_datetime(trading_df[RevolutTradingFile.DATE], format="ISO8601", utc=True)
    last = parsed.max()
    if pd.isna(last):
        return valuation_date.isoformat()
    if last.tzinfo:
        return last.tz_convert(None).date().isoformat()
    return last.date().isoformat()


def _currency(trading_df: pd.DataFrame, holdings: dict[str, dict]) -> str | None:
    currencies = {info.get("currency") for info in holdings.values() if info.get("currency")}
    if len(currencies) == 1:
        return next(iter(currencies))
    if RevolutTradingFile.CURRENCY not in trading_df.columns:
        return None
    values = trading_df[RevolutTradingFile.CURRENCY].dropna().astype(str).str.strip()
    values = values[values.ne("")]
    if len(values):
        return str(values.iloc[0])
    return None
