# -*- coding: utf-8 -*-
"""ROI depozytu Trade Republic (CAPEX/DIVESTMENT z amount; odsetki tylko w NAV/terminal)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from app_proc.data_root import get_online_data_root, resolve_asset_dir
from evaluators.valuation_date import filter_on_or_before
from importers.assets.data_model import TypeDomain
from importers.traderepublic.data_model import (
    DEFAULT_TRADEREPUBLIC_ASSET_ID,
    TradeRepublicFile,
)
from importers.traderepublic.read_traderepublic import read_traderepublic_transactions
from roi.categories import CAPEX, DIVESTMENT
from roi.compute_roi import roi_summary_to_row
from roi.data_model import CashFlowEvent
from roi.revolut_deposit_roi import compute_deposit_roi
from roi.statement_valuation_date import attach_evaluation_date, evaluation_date_from_frame


def _num(value) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0.0
    if isinstance(value, str) and not str(value).strip():
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def row_nav_contribution(row: pd.Series) -> float:
    """AMOUNT − |FEE| − |TAX| (koszty jako wielkości nieujemne)."""
    return _num(row.get(TradeRepublicFile.AMOUNT)) - abs(
        _num(row.get(TradeRepublicFile.FEE))
    ) - abs(_num(row.get(TradeRepublicFile.TAX)))


def nav_as_of(blotter: pd.DataFrame, valuation_date: date) -> tuple[float, list[str]]:
    """NAV_t = Σ (amount − |fee| − |tax|) dla date ≤ t; nieznane type → warning, poza sumą."""
    warnings: list[str] = []
    if blotter is None or blotter.empty:
        return 0.0, warnings

    filtered = filter_on_or_before(blotter, TradeRepublicFile.DATE, valuation_date)
    if filtered.empty:
        return 0.0, warnings

    known = {
        TradeRepublicFile.TYPE_CUSTOMER_INPAYMENT,
        TradeRepublicFile.TYPE_CUSTOMER_OUTPAYMENT,
        TradeRepublicFile.TYPE_INTEREST_PAYMENT,
    }
    total = 0.0
    unknown: set[str] = set()
    for _, row in filtered.iterrows():
        tx_type = str(row.get(TradeRepublicFile.TYPE) or "").strip()
        if tx_type not in known:
            if tx_type:
                unknown.add(tx_type)
            continue
        total += row_nav_contribution(row)

    for tx_type in sorted(unknown):
        warnings.append(
            f"Trade Republic: nieznany type {tx_type!r} poza NAV / CF depozytu"
        )
    return float(total), warnings


def build_traderepublic_cashflows(
    blotter: pd.DataFrame,
    asset_id: str,
) -> tuple[pd.DataFrame, list[str]]:
    """
    CF z kolumny AMOUNT:
    CUSTOMER_INPAYMENT → CAPEX −abs; CUSTOMER_OUTPAYMENT → DIVESTMENT +abs;
    INTEREST_PAYMENT poza CF.
    """
    empty = pd.DataFrame(columns=list(CashFlowEvent.COLUMN_ORDER))
    warnings: list[str] = []
    if blotter is None or blotter.empty:
        return empty, warnings

    known_cf = {
        TradeRepublicFile.TYPE_CUSTOMER_INPAYMENT,
        TradeRepublicFile.TYPE_CUSTOMER_OUTPAYMENT,
    }
    known_skip = {TradeRepublicFile.TYPE_INTEREST_PAYMENT}
    rows: list[dict] = []
    unknown: set[str] = set()

    for _, row in blotter.iterrows():
        tx_type = str(row.get(TradeRepublicFile.TYPE) or "").strip()
        event_date = str(row.get(TradeRepublicFile.DATE) or "").strip()
        if tx_type in known_skip:
            continue
        if tx_type not in known_cf:
            if tx_type:
                unknown.add(tx_type)
            continue
        amount_raw = _num(row.get(TradeRepublicFile.AMOUNT))
        if abs(amount_raw) <= 1e-12:
            continue
        if tx_type == TradeRepublicFile.TYPE_CUSTOMER_INPAYMENT:
            category = CAPEX
            amount = -abs(amount_raw)
        else:
            category = DIVESTMENT
            amount = abs(amount_raw)
        rows.append(
            {
                CashFlowEvent.ASSET_ID: asset_id,
                CashFlowEvent.DATE: event_date,
                CashFlowEvent.AMOUNT: float(amount),
                CashFlowEvent.CATEGORY: category,
                CashFlowEvent.SOURCE: asset_id,
                CashFlowEvent.DESCRIPTION: tx_type,
                CashFlowEvent.TITLE: str(row.get(TradeRepublicFile.DESCRIPTION) or ""),
                CashFlowEvent.COUNTERPARTY: "",
                CashFlowEvent.ACCOUNT_NUMBER: "",
            }
        )

    for tx_type in sorted(unknown):
        warnings.append(
            f"Trade Republic: nieznany type {tx_type!r} poza NAV / CF depozytu"
        )

    if not rows:
        return empty, warnings
    result = pd.DataFrame(rows, columns=list(CashFlowEvent.COLUMN_ORDER))
    CashFlowEvent.check_structure(result)
    return result, warnings


def compute_traderepublic_roi(
    valuation_date: date,
    *,
    assets_root: Path | None = None,
    asset_id: str = DEFAULT_TRADEREPUBLIC_ASSET_ID,
    blotter: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], list[str]]:
    """Summary + mapa eventów dla `p_traderepublic` (terminal = NAV_t)."""
    warnings: list[str] = []
    events_by_asset: dict[str, pd.DataFrame] = {}

    if blotter is None:
        root = assets_root or get_online_data_root()
        asset_dir = root / asset_id
        if not asset_dir.is_dir():
            # Fallback jak ewaluator — resolve_asset_dir dla typów investment.*
            try:
                asset_dir = resolve_asset_dir(asset_id, TypeDomain.EQUITIES)
            except Exception:
                return pd.DataFrame(), events_by_asset, warnings
        if not asset_dir.is_dir():
            return pd.DataFrame(), events_by_asset, warnings
        try:
            blotter = read_traderepublic_transactions(asset_dir, asset_id)
        except ValueError as exc:
            warnings.append(f"[{asset_id}] {exc}")
            return pd.DataFrame(), events_by_asset, warnings

    if blotter is None or blotter.empty:
        return pd.DataFrame(), events_by_asset, warnings

    cashflows, cf_warnings = build_traderepublic_cashflows(blotter, asset_id)
    warnings.extend(cf_warnings)
    if cashflows.empty:
        warnings.append(f"[{asset_id}] Brak operacji wpłaty/wypłaty w eksporcie TR")
        return pd.DataFrame(), events_by_asset, warnings

    terminal, nav_warnings = nav_as_of(blotter, valuation_date)
    # Unikaj duplikatu warningów type (CF już ostrzegł).
    for w in nav_warnings:
        if w not in warnings:
            warnings.append(w)

    used = filter_on_or_before(blotter, TradeRepublicFile.DATE, valuation_date)
    eval_date = evaluation_date_from_frame(
        used, TradeRepublicFile.FILE_DATE, valuation_date
    )
    summary = compute_deposit_roi(
        asset_id,
        cashflows,
        valuation_date,
        terminal_unrealized=terminal,
    )
    events_by_asset[asset_id] = cashflows
    row = attach_evaluation_date(roi_summary_to_row(summary), eval_date)
    return pd.DataFrame([row]), events_by_asset, warnings
