# -*- coding: utf-8 -*-
"""ROI depozytów Revolut z savings-statement (CAPEX −abs, DIVESTMENT +abs; odsetki poza CF)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from app_proc.data_root import get_cash_pool_root
from evaluators.valuation_date import filter_excel_rows_on_or_before, filter_on_or_before
from importers.revolut.deposit_data_model import RevolutDepositFile
from importers.revolut.read_r_deposits import read_revolut_deposit_transactions
from importers.revolut.savings_statement import (
    OPIS_DEPOSIT,
    OPIS_INTEREST,
    OPIS_WITHDRAWAL,
)
from roi.categories import CAPEX, DIVESTMENT, OPEX, REVENUES
from roi.compute_roi import RoiSummary, _aggregate_category, roi_summary_to_row
from roi.data_model import CashFlowEvent
from roi.xirr import cashflows_for_xirr, compute_xirr

DEPOSIT_ASSET_IDS = ("p_re_eur", "p_re_pln", "g_re_eur", "g_re_pln")
TAX_RATE = 0.19
BALANCE_EPS = 1e-9


def tax_liability_asset_id(deposit_id: str, year: int) -> str:
    return f"{deposit_id}_zobowiazanie_podatkowe_{year}"


def latest_deposit_balance(deposit_df: pd.DataFrame, valuation_date: date) -> float:
    filtered = filter_on_or_before(deposit_df, RevolutDepositFile.DATE, valuation_date)
    if filtered.empty:
        return 0.0
    return float(filtered.iloc[-1][RevolutDepositFile.BALANCE])


def build_deposit_cashflows(deposit_df: pd.DataFrame, asset_id: str) -> pd.DataFrame:
    empty = pd.DataFrame(columns=list(CashFlowEvent.COLUMN_ORDER))
    if deposit_df is None or deposit_df.empty:
        return empty

    rows: list[dict] = []
    for _, row in deposit_df.iterrows():
        opis = str(row[RevolutDepositFile.DESCRIPTION]).strip()
        event_date = str(row[RevolutDepositFile.DATE])
        if opis == OPIS_DEPOSIT:
            amount_raw = row[RevolutDepositFile.MONEY_IN]
            if pd.isna(amount_raw):
                continue
            category = CAPEX
            amount = -abs(float(amount_raw))
        elif opis == OPIS_INTEREST:
            # Naliczenie odsetek nie jest CF — wchodzi w Saldo/terminal, nie do XIRR.
            continue
        elif opis == OPIS_WITHDRAWAL:
            amount_raw = row[RevolutDepositFile.MONEY_OUT]
            if pd.isna(amount_raw):
                continue
            category = DIVESTMENT
            amount = abs(float(amount_raw))
        else:
            continue

        rows.append(
            {
                CashFlowEvent.ASSET_ID: asset_id,
                CashFlowEvent.DATE: event_date,
                CashFlowEvent.AMOUNT: float(amount),
                CashFlowEvent.CATEGORY: category,
                CashFlowEvent.SOURCE: asset_id,
                CashFlowEvent.DESCRIPTION: opis,
                CashFlowEvent.TITLE: "",
                CashFlowEvent.COUNTERPARTY: "",
                CashFlowEvent.ACCOUNT_NUMBER: "",
            }
        )

    if not rows:
        return empty
    result = pd.DataFrame(rows, columns=list(CashFlowEvent.COLUMN_ORDER))
    CashFlowEvent.check_structure(result)
    return result


def build_tax_liability_cashflows(
    deposit_df: pd.DataFrame,
    deposit_id: str,
    year: int,
) -> pd.DataFrame:
    empty = pd.DataFrame(columns=list(CashFlowEvent.COLUMN_ORDER))
    if deposit_df is None or deposit_df.empty:
        return empty

    tax_id = tax_liability_asset_id(deposit_id, year)
    rows: list[dict] = []
    for _, row in deposit_df.iterrows():
        if str(row[RevolutDepositFile.DESCRIPTION]).strip() != OPIS_INTEREST:
            continue
        event_date = str(row[RevolutDepositFile.DATE])
        try:
            event_year = date.fromisoformat(event_date).year
        except ValueError:
            continue
        if event_year != year:
            continue
        amount_raw = row[RevolutDepositFile.MONEY_IN]
        if pd.isna(amount_raw):
            continue
        brutto = abs(float(amount_raw))
        rows.append(
            {
                CashFlowEvent.ASSET_ID: tax_id,
                CashFlowEvent.DATE: event_date,
                CashFlowEvent.AMOUNT: -TAX_RATE * brutto,
                CashFlowEvent.CATEGORY: OPEX,
                CashFlowEvent.SOURCE: deposit_id,
                CashFlowEvent.DESCRIPTION: f"Belka {int(TAX_RATE * 100)}% od {OPIS_INTEREST}",
                CashFlowEvent.TITLE: "",
                CashFlowEvent.COUNTERPARTY: "",
                CashFlowEvent.ACCOUNT_NUMBER: "",
            }
        )

    if not rows:
        return empty
    result = pd.DataFrame(rows, columns=list(CashFlowEvent.COLUMN_ORDER))
    CashFlowEvent.check_structure(result)
    return result


def tax_liability_value(deposit_df: pd.DataFrame, valuation_date: date) -> float:
    """Ujemna zaległość = −19% × Σ oprocentowania brutto w roku wyceny ≤ data."""
    year = valuation_date.year
    filtered = filter_on_or_before(deposit_df, RevolutDepositFile.DATE, valuation_date)
    if filtered.empty:
        return 0.0
    interest = filtered[filtered[RevolutDepositFile.DESCRIPTION] == OPIS_INTEREST]
    if interest.empty:
        return 0.0
    total = 0.0
    for _, row in interest.iterrows():
        try:
            if date.fromisoformat(str(row[RevolutDepositFile.DATE])).year != year:
                continue
        except ValueError:
            continue
        amount_raw = row[RevolutDepositFile.MONEY_IN]
        if pd.isna(amount_raw):
            continue
        total += abs(float(amount_raw))
    return -TAX_RATE * total


def compute_deposit_roi(
    asset_id: str,
    cashflows: pd.DataFrame,
    valuation_date: date,
    *,
    terminal_unrealized: float,
) -> RoiSummary:
    filtered = filter_excel_rows_on_or_before(cashflows, CashFlowEvent.DATE, valuation_date)
    capex = _aggregate_category(filtered, CAPEX)
    opex = _aggregate_category(filtered, OPEX)
    revenue = _aggregate_category(filtered, REVENUES)
    if filtered.empty:
        terminal_realized = 0.0
    else:
        mask = filtered[CashFlowEvent.CATEGORY] == DIVESTMENT
        terminal_realized = float(filtered.loc[mask, CashFlowEvent.AMOUNT].sum())

    sold = abs(terminal_unrealized) <= BALANCE_EPS
    terminal = 0.0 if sold else float(terminal_unrealized)
    flows_total = float(filtered[CashFlowEvent.AMOUNT].sum()) if not filtered.empty else 0.0
    roi_nominal = flows_total + terminal

    xirr_dates, xirr_amounts = cashflows_for_xirr(filtered, valuation_date, terminal)
    xirr = compute_xirr(xirr_dates, xirr_amounts)

    return RoiSummary(
        asset_id=asset_id,
        capex=capex,
        opex=opex,
        revenue=revenue,
        terminal_realized=terminal_realized,
        terminal_unrealized=terminal,
        roi_nominal=roi_nominal,
        xirr=xirr,
        is_sold=sold,
        warnings=[],
    )


def compute_tax_liability_roi(
    asset_id: str,
    cashflows: pd.DataFrame,
    valuation_date: date,
) -> RoiSummary:
    """Zobowiązanie: tylko OPEX (−19%); terminal 0; XIRR zwykle niedostępny."""
    filtered = filter_excel_rows_on_or_before(cashflows, CashFlowEvent.DATE, valuation_date)
    opex = _aggregate_category(filtered, OPEX)
    flows_total = float(filtered[CashFlowEvent.AMOUNT].sum()) if not filtered.empty else 0.0
    xirr_dates, xirr_amounts = cashflows_for_xirr(filtered, valuation_date, 0.0)
    xirr = compute_xirr(xirr_dates, xirr_amounts)
    return RoiSummary(
        asset_id=asset_id,
        capex=0.0,
        opex=opex,
        revenue=0.0,
        terminal_realized=0.0,
        terminal_unrealized=0.0,
        roi_nominal=flows_total,
        xirr=xirr,
        is_sold=False,
        warnings=[],
    )


def compute_revolut_deposit_roi(
    valuation_date: date,
    *,
    cash_pool_root: Path | None = None,
    asset_ids: tuple[str, ...] = DEPOSIT_ASSET_IDS,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], list[str]]:
    root = cash_pool_root or get_cash_pool_root()
    warnings: list[str] = []
    summary_rows: list[dict] = []
    events_by_asset: dict[str, pd.DataFrame] = {}
    year = valuation_date.year

    for asset_id in asset_ids:
        asset_dir = root / asset_id
        if not asset_dir.is_dir():
            continue
        try:
            deposit_df = read_revolut_deposit_transactions(asset_dir, asset_id)
        except ValueError as exc:
            warnings.append(f"[{asset_id}] {exc}")
            continue

        if deposit_df.empty:
            continue

        deposit_cf = build_deposit_cashflows(deposit_df, asset_id)
        if deposit_cf.empty:
            warnings.append(f"[{asset_id}] Brak operacji Depozyt/Wypłata w savings")
            continue

        terminal = latest_deposit_balance(deposit_df, valuation_date)
        summary = compute_deposit_roi(
            asset_id,
            deposit_cf,
            valuation_date,
            terminal_unrealized=terminal,
        )
        summary_rows.append(roi_summary_to_row(summary))
        events_by_asset[asset_id] = deposit_cf

        tax_cf = build_tax_liability_cashflows(deposit_df, asset_id, year)
        if not tax_cf.empty:
            tax_id = tax_liability_asset_id(asset_id, year)
            tax_summary = compute_tax_liability_roi(tax_id, tax_cf, valuation_date)
            summary_rows.append(roi_summary_to_row(tax_summary))
            events_by_asset[tax_id] = tax_cf

    if not summary_rows:
        return pd.DataFrame(), events_by_asset, warnings

    summary = pd.DataFrame(summary_rows)
    return summary, events_by_asset, warnings
