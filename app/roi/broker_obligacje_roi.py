# -*- coding: utf-8 -*-
"""ROI per KOD OBLIGACJI — cashflow wyłącznie z rejestru przepływy pieniężne."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from app_proc.data_root import resolve_asset_dir
from evaluators.evaluate_broker_obligacje import DEFAULT_BONDS_BROKER_ID
from importers.assets.data_model import AssetsDef, KindDomain, TypeDomain
from importers.assets.read_assets import read_assets
from importers.pkobp.data_model import PkoBpBonds, PkoBpStan
from importers.pkobp.read_historia import (
    filter_cashflow_register,
    filter_historia_on_or_before,
    open_qty_by_code,
    read_obligacje_historia,
)
from importers.pkobp.read_stan import read_obligacje_stan, select_stan_as_of
from roi.broker_trading_roi import compute_ticker_roi, ticker_asset_id
from roi.categories import CAPEX, DIVESTMENT, OPEX
from roi.compute_roi import roi_summary_to_row
from roi.data_model import CashFlowEvent


def _roi_category(order_type: str) -> str | None:
    """
    Tylko prawdziwe CF (nie kategorie ekonomiczne typu naliczenie/podatek).
    Odsetki i podatek siedzą już w MTM (WARTOŚĆ AKTUALNA) — w CF dublowałyby wynik.
    Znak w 01 source: CAPEX −, OPEX/DIVESTMENT +.
    CAPEX — zakup papierów
    OPEX — opłata za przedterminowy wykup
    DIVESTMENT — wypłata przelewem (zwrot kapitału)
    """
    t = order_type.strip()
    if t == "zakup papierów":
        return CAPEX
    if t == "opłata za przedterminowy wykup":
        return OPEX
    if t == "wypłata przelewem":
        return DIVESTMENT
    return None


def build_bonds_cashflows(historia: pd.DataFrame, broker_id: str) -> dict[str, pd.DataFrame]:
    empty_cols = list(CashFlowEvent.COLUMN_ORDER)
    if historia is None or historia.empty:
        return {}

    cashflows = filter_cashflow_register(historia)
    by_code: dict[str, list[dict]] = {}
    for _, row in cashflows.iterrows():
        order_type = str(row[PkoBpBonds.ORDER_TYPE]).strip()
        code = row.get(PkoBpBonds.CODE)
        if pd.isna(code) or not str(code).strip():
            continue
        code = str(code).strip()
        amount_raw = pd.to_numeric(row[PkoBpBonds.AMOUNT], errors="coerce")
        if pd.isna(amount_raw):
            continue
        category = _roi_category(order_type)
        if category is None:
            continue
        event_date = _historia_date_str(row[PkoBpBonds.DATE])
        if event_date is None:
            continue

        asset_id = ticker_asset_id(broker_id, code)
        by_code.setdefault(code, []).append(
            {
                CashFlowEvent.ASSET_ID: asset_id,
                CashFlowEvent.DATE: event_date,
                CashFlowEvent.AMOUNT: float(amount_raw),
                CashFlowEvent.CATEGORY: category,
                CashFlowEvent.SOURCE: broker_id,
                CashFlowEvent.DESCRIPTION: order_type,
                CashFlowEvent.TITLE: code,
                CashFlowEvent.COUNTERPARTY: "",
                CashFlowEvent.ACCOUNT_NUMBER: "",
            }
        )

    result: dict[str, pd.DataFrame] = {}
    for code, rows in by_code.items():
        df = pd.DataFrame(rows, columns=empty_cols)
        CashFlowEvent.check_structure(df)
        result[ticker_asset_id(broker_id, code)] = df
    return result


def terminal_by_code(
    stan_as_of: pd.DataFrame,
    open_qty: dict[str, float],
) -> dict[str, dict]:
    """Per kod: qty, terminal (WARTOŚĆ AKTUALNA lub unit_price×qty), last_price."""
    mtm: dict[str, dict] = {}
    if stan_as_of is not None and not stan_as_of.empty:
        for _, row in stan_as_of.iterrows():
            code = str(row[PkoBpStan.EMISSION]).strip()
            value = float(pd.to_numeric(row[PkoBpStan.CURRENT_VALUE], errors="coerce") or 0.0)
            unit = pd.to_numeric(row[PkoBpStan.UNIT_PRICE], errors="coerce")
            avail = float(pd.to_numeric(row[PkoBpStan.QTY_AVAILABLE], errors="coerce") or 0.0)
            blocked = float(pd.to_numeric(row[PkoBpStan.QTY_BLOCKED], errors="coerce") or 0.0)
            qty = avail + blocked
            mtm[code] = {
                "qty": qty,
                "terminal": value,
                "last_price": float(unit) if pd.notna(unit) and qty else 0.0,
            }

    codes = set(open_qty) | set(mtm)
    state: dict[str, dict] = {}
    for code in codes:
        qty = float(open_qty.get(code, mtm.get(code, {}).get("qty", 0.0)))
        if code in mtm:
            terminal = float(mtm[code]["terminal"])
            last_price = float(mtm[code]["last_price"])
            if last_price == 0.0 and qty > 0 and terminal:
                last_price = terminal / qty
        else:
            terminal = 0.0
            last_price = 0.0
        state[code] = {"qty": qty, "terminal": terminal, "last_price": last_price}
    return state


def compute_bonds_broker_roi_from_frames(
    historia: pd.DataFrame,
    stan_df: pd.DataFrame,
    valuation_date: date,
    broker_id: str = DEFAULT_BONDS_BROKER_ID,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    filtered = filter_historia_on_or_before(historia, valuation_date)
    events_by_asset = build_bonds_cashflows(filtered, broker_id)
    open_qty = open_qty_by_code(filtered)
    stan_as_of = select_stan_as_of(stan_df, valuation_date)
    state = terminal_by_code(stan_as_of, open_qty)

    for code, st in state.items():
        asset_id = ticker_asset_id(broker_id, code)
        if asset_id not in events_by_asset and abs(st["qty"]) > 1e-12:
            events_by_asset[asset_id] = pd.DataFrame(columns=list(CashFlowEvent.COLUMN_ORDER))

    rows = []
    for asset_id, events in sorted(events_by_asset.items()):
        code = asset_id.split(":", 1)[-1]
        st = state.get(code, {"qty": 0.0, "terminal": 0.0, "last_price": 0.0})
        qty = float(st["qty"])
        if abs(qty) > 1e-12:
            last_price = float(st["terminal"]) / qty if qty else 0.0
        else:
            last_price = 0.0
        summary = compute_ticker_roi(
            asset_id,
            events,
            valuation_date,
            open_qty=qty,
            last_price=last_price,
        )
        rows.append(roi_summary_to_row(summary))

    return pd.DataFrame(rows), events_by_asset


def compute_obligacje_broker_roi(
    valuation_date: date,
    *,
    broker_id: str = DEFAULT_BONDS_BROKER_ID,
    historia: pd.DataFrame | None = None,
    stan_df: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], list[str]]:
    warnings: list[str] = []
    if historia is None or stan_df is None:
        assets = read_assets()
        rows = assets[assets[AssetsDef.ID].astype(str) == broker_id]
        if rows.empty:
            broker_mask = assets[AssetsDef.KIND].astype(str).str.startswith(KindDomain.BROKER)
            bonds_mask = assets[AssetsDef.TYPE].astype(str) == TypeDomain.BONDS
            rows = assets.loc[broker_mask & bonds_mask]
            rows = rows[rows[AssetsDef.ID].astype(str) == broker_id]
        if rows.empty:
            raise ValueError(f"Brak aktywa brokerskiego {broker_id!r} w a_config.xlsx (arkusz assets)")
        row = rows.iloc[0]
        asset_dir = resolve_asset_dir(broker_id, row[AssetsDef.TYPE])
        if not Path(asset_dir).is_dir():
            raise ValueError(f"Brak katalogu brokera: {asset_dir}")
        if historia is None:
            historia = read_obligacje_historia(asset_dir, broker_id)
        if stan_df is None:
            stan_df = read_obligacje_stan(asset_dir, broker_id)

    summary, events = compute_bonds_broker_roi_from_frames(
        historia, stan_df, valuation_date, broker_id
    )
    if summary.empty:
        warnings.append(f"Brak danych ROI dla {broker_id}")
    return summary, events, warnings


def _historia_date_str(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.date().isoformat()
