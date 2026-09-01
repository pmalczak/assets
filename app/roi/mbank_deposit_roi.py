# -*- coding: utf-8 -*-
"""ROI lokat mBank per NR (CAPEX otwarcie, DIVESTMENT zerwanie/wygaśnięcie, odsetki/podatek w CF)."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pandas as pd

from app_proc.data_root import resolve_asset_dir
from evaluators.valuation_date import filter_excel_rows_on_or_before, filter_on_or_before
from importers.assets.data_model import AssetsDef, KindDomain
from importers.assets.read_assets import read_assets
from importers.mbank.data_model import MBankFile, MbankOperationType
from importers.mbank.read_m_transactions import read_m_transactions
from roi.categories import CAPEX, DIVESTMENT, OPEX, REVENUES
from roi.compute_roi import RoiSummary, _aggregate_category, roi_summary_to_row
from roi.data_model import CashFlowEvent
from roi.xirr import cashflows_for_xirr, compute_xirr

LOKATA_NR_RE = re.compile(r"\bNR \d{15}\b")
OTW_LOKATY = "OTW. LOKATY"

_CLOSE_OPS = {
    MbankOperationType.ZERWANIE_LOKATY_TERMINOWEJ,
    MbankOperationType.WYGASNIECIE_LOKATY_TERMINOWEJ,
}
_MAPPED_OPS = _CLOSE_OPS | {
    MbankOperationType.ODSETKI_LOKAT_TERMINOWYCH,
    MbankOperationType.PODATEK_OD_ODSETEK_KAPITALOWYCH,
}


def extract_lokata_nr(title: object) -> str | None:
    if title is None or (isinstance(title, float) and pd.isna(title)):
        return None
    match = LOKATA_NR_RE.search(str(title).strip())
    if match is None:
        return None
    return match.group(0)


def lokata_asset_id(account_id: str, nr: str) -> str:
    return f"{str(account_id).strip()}:{str(nr).strip()}"


def _event_date_str(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.date().isoformat()


def _amount(value) -> float | None:
    amount = pd.to_numeric(value, errors="coerce")
    if pd.isna(amount):
        return None
    return float(amount)


def _roi_category(opis: str, title: str) -> str | None:
    if opis == MbankOperationType.PRZELEW_WEWNETRZNY_WYCHODZACY and OTW_LOKATY in title:
        return CAPEX
    if opis in _CLOSE_OPS:
        return DIVESTMENT
    if opis == MbankOperationType.ODSETKI_LOKAT_TERMINOWYCH:
        return REVENUES
    if opis == MbankOperationType.PODATEK_OD_ODSETEK_KAPITALOWYCH:
        return OPEX
    return None


def build_mbank_lokata_cashflows(
    statement: pd.DataFrame,
    account_id: str,
) -> tuple[dict[str, pd.DataFrame], list[str]]:
    """CF per NR. Nieznany opis przy prawdziwym NR → warning, nie cichy skip."""
    empty_cols = list(CashFlowEvent.COLUMN_ORDER)
    warnings: list[str] = []
    if statement is None or statement.empty:
        return {}, warnings

    mapped: dict[str, list[dict]] = {}
    pending_unknown: list[tuple[str, str]] = []

    for _, row in statement.iterrows():
        title = str(row.get(MBankFile.MBANK_TITLE) or "").strip()
        nr = extract_lokata_nr(title)
        if nr is None:
            continue
        opis = str(row.get(MBankFile.MBANK_DESCRIPTION) or "").strip()
        category = _roi_category(opis, title)
        if category is None:
            pending_unknown.append((nr, opis))
            continue
        amount = _amount(row.get(MBankFile.MBANK_AMOUNT))
        if amount is None:
            continue
        event_date = _event_date_str(row.get(MBankFile.MBANK_TRANSACTION_DATE))
        if event_date is None:
            continue
        asset_id = lokata_asset_id(account_id, nr)
        mapped.setdefault(nr, []).append(
            {
                CashFlowEvent.ASSET_ID: asset_id,
                CashFlowEvent.DATE: event_date,
                CashFlowEvent.AMOUNT: amount,
                CashFlowEvent.CATEGORY: category,
                CashFlowEvent.SOURCE: account_id,
                CashFlowEvent.DESCRIPTION: opis,
                CashFlowEvent.TITLE: title,
                CashFlowEvent.COUNTERPARTY: str(row.get(MBankFile.MBANK_TRANSACTION_PARTY) or ""),
                CashFlowEvent.ACCOUNT_NUMBER: str(row.get(MBankFile.MBANK_ACCOUNT_NUMBER) or ""),
            }
        )

    known_nrs = set(mapped)
    seen_unknown: set[tuple[str, str]] = set()
    for nr, opis in pending_unknown:
        if nr not in known_nrs:
            continue
        key = (nr, opis)
        if key in seen_unknown:
            continue
        seen_unknown.add(key)
        warnings.append(
            f"[{lokata_asset_id(account_id, nr)}] Nieznany opis lokaty {opis!r} — poza CF"
        )

    result: dict[str, pd.DataFrame] = {}
    for nr, rows in mapped.items():
        df = pd.DataFrame(rows, columns=empty_cols)
        CashFlowEvent.check_structure(df)
        result[lokata_asset_id(account_id, nr)] = df
    return result, warnings


def compute_lokata_roi(
    asset_id: str,
    cashflows: pd.DataFrame,
    valuation_date: date,
) -> RoiSummary:
    filtered = filter_excel_rows_on_or_before(cashflows, CashFlowEvent.DATE, valuation_date)
    capex = _aggregate_category(filtered, CAPEX)
    opex = _aggregate_category(filtered, OPEX)
    revenue = _aggregate_category(filtered, REVENUES)
    if filtered.empty:
        terminal_realized = 0.0
        sold = False
    else:
        divest_mask = filtered[CashFlowEvent.CATEGORY] == DIVESTMENT
        terminal_realized = float(filtered.loc[divest_mask, CashFlowEvent.AMOUNT].sum())
        sold = bool(divest_mask.any())

    warnings: list[str] = []
    if sold:
        n_divest = int((filtered[CashFlowEvent.CATEGORY] == DIVESTMENT).sum())
        if n_divest > 1:
            warnings.append(f"[{asset_id}] Więcej niż jeden DIVESTMENT ({n_divest})")
        terminal = 0.0
    else:
        terminal = -float(capex)

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
        warnings=warnings,
    )


def _load_mbank_statements() -> tuple[dict[str, pd.DataFrame], list[str]]:
    warnings: list[str] = []
    assets = read_assets()
    kind = assets[AssetsDef.KIND].astype(str)
    rows = assets.loc[kind.str.startswith(KindDomain.MBANK)]
    statements: dict[str, pd.DataFrame] = {}
    for _, asset_row in rows.iterrows():
        account_id = str(asset_row[AssetsDef.ID]).strip()
        asset_dir = resolve_asset_dir(account_id, asset_row[AssetsDef.TYPE])
        if not Path(asset_dir).is_dir():
            warnings.append(f"[{account_id}] Brak katalogu {asset_dir}")
            continue
        try:
            statements[account_id] = read_m_transactions(asset_dir, account_id)
        except ValueError as exc:
            warnings.append(f"[{account_id}] {exc}")
    return statements, warnings


def compute_mbank_deposit_roi(
    valuation_date: date,
    *,
    statements: dict[str, pd.DataFrame] | None = None,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], list[str]]:
    warnings: list[str] = []
    if statements is None:
        statements, load_warnings = _load_mbank_statements()
        warnings.extend(load_warnings)

    summary_rows: list[dict] = []
    events_by_asset: dict[str, pd.DataFrame] = {}

    for account_id, raw in sorted(statements.items()):
        filtered = filter_on_or_before(raw, MBankFile.MBANK_TRANSACTION_DATE, valuation_date)
        events, cf_warnings = build_mbank_lokata_cashflows(filtered, account_id)
        warnings.extend(cf_warnings)
        for asset_id, cashflows in sorted(events.items()):
            summary = compute_lokata_roi(asset_id, cashflows, valuation_date)
            warnings.extend(f"{msg}" for msg in summary.warnings)
            summary_rows.append(roi_summary_to_row(summary))
            events_by_asset[asset_id] = cashflows

    if not summary_rows:
        return pd.DataFrame(), events_by_asset, warnings
    return pd.DataFrame(summary_rows), events_by_asset, warnings
