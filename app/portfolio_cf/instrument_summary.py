# -*- coding: utf-8 -*-
"""Podsumowanie per-instrument (jak tabela ROI) z ledgera portfolio_cf w PLN."""
from __future__ import annotations

from datetime import date

import pandas as pd

from evaluators.valuation_date import filter_excel_rows_on_or_before
from importers.assets.data_model import AssetsDef
from portfolio_cf.allocate import allocate_ledger_to_portfolio
from portfolio_cf.assemble import AssemblyResult
from portfolio_cf.data_model import InstrumentCashFlow, cash_instrument_id
from portfolio_cf.fx import to_pln
from portfolio_cf.sold_status import (
    filter_ledger_by_sold,
    is_instrument_sold,
    sold_filter_label,
)
from portfolios.composition import KIND_CASH, KIND_POSITION, load_gm_position_lines
from roi.aggregate_venue_roi import aggregate_venue_roi
from roi.categories import CAPEX, DIVESTMENT, OPEX, REVENUES
from roi.compute_roi import RoiSummary, roi_summary_to_row
from roi.data_model import CashFlowEvent
from roi.xirr import cashflows_for_xirr, compute_xirr


def _implied_fx_pln(snapshot: pd.DataFrame, broker_id: str, currency: str) -> float:
    code = str(currency or "").strip().upper()
    if not code or code == "PLN":
        return 1.0
    if snapshot is None or snapshot.empty or AssetsDef.ID not in snapshot.columns:
        return 1.0
    rows = snapshot.loc[snapshot[AssetsDef.ID].astype(str).str.strip() == str(broker_id)]
    if rows.empty:
        return 1.0
    native = pd.to_numeric(rows.iloc[0].get(AssetsDef.VALUE), errors="coerce")
    pln = pd.to_numeric(rows.iloc[0].get(AssetsDef.VALUE_PLN), errors="coerce")
    if pd.isna(native) or float(native) == 0.0 or pd.isna(pln):
        return 1.0
    return float(pln) / float(native)


def build_portfolio_instrument_summary(
    assembly: AssemblyResult,
    portfolio_name: str,
    valuation_date: date,
    *,
    snapshot: pd.DataFrame | None = None,
    sold_filter: str | None = None,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Tabela jak w ROI: CAPEX/OPEX/REVENUES/DIVESTMENT/terminal/XIRR w PLN.

    Kwoty z ``amount_pln`` ledgera; terminal nerealiz. z snapshota / pozycji GM /
    venue ROI (przeliczone na PLN). Wiersze posortowane po ``asset_id``.
    """
    mode = sold_filter if sold_filter is not None else sold_filter_label()
    subset = allocate_ledger_to_portfolio(assembly.ledger, portfolio_name)
    subset = filter_ledger_by_sold(
        subset, assembly.is_sold_by_instrument, sold_filter=mode
    )
    if subset is None or subset.empty:
        return pd.DataFrame(), {}

    terminal_pln, eval_dates = resolve_terminal_pln_by_instrument(
        valuation_date,
        snapshot=snapshot,
        ledger=subset,
    )
    instrument_labels = _instrument_labels(subset)

    rows: list[dict] = []
    events_by_asset: dict[str, pd.DataFrame] = {}
    for instrument_id, group in subset.groupby(
        subset[InstrumentCashFlow.INSTRUMENT_ID].astype(str), sort=True
    ):
        events = _ledger_group_to_pln_events(instrument_id, group)
        events_by_asset[instrument_id] = events
        sold = is_instrument_sold(instrument_id, assembly.is_sold_by_instrument)
        terminal_unrealized = 0.0 if sold else float(terminal_pln.get(instrument_id, 0.0))
        row = _summary_row_from_pln_events(
            instrument_id,
            events,
            valuation_date,
            terminal_unrealized=terminal_unrealized,
            is_sold=sold,
            evaluation_date=eval_dates.get(instrument_id) or "",
        )
        label = instrument_labels.get(instrument_id)
        if label:
            row["instrument"] = label
        rows.append(row)

    if not rows:
        return pd.DataFrame(), {}
    summary = pd.DataFrame(rows)
    return summary.reset_index(drop=True), events_by_asset


def aggregate_portfolio_instrument_summary(
    summary: pd.DataFrame,
    events_by_asset: dict[str, pd.DataFrame],
    valuation_date: date,
) -> pd.DataFrame:
    """Wiersz Razem — te same reguły co ``aggregate_venue_roi`` (kwoty PLN)."""
    return aggregate_venue_roi(summary, events_by_asset, valuation_date)


def resolve_terminal_pln_by_instrument(
    valuation_date: date,
    *,
    snapshot: pd.DataFrame | None = None,
    ledger: pd.DataFrame | None = None,
) -> tuple[dict[str, float], dict[str, str]]:
    """Mapa instrument_id → terminal PLN + data wyceny (best-effort)."""
    terminals: dict[str, float] = {}
    eval_dates: dict[str, str] = {}

    if snapshot is not None and not snapshot.empty and AssetsDef.ID in snapshot.columns:
        for _, row in snapshot.iterrows():
            key = str(row[AssetsDef.ID]).strip()
            if not key:
                continue
            value = pd.to_numeric(row.get(AssetsDef.VALUE_PLN), errors="coerce")
            if pd.isna(value):
                continue
            terminals[key] = float(value)
            eval_raw = row.get(AssetsDef.EVALUATION_DATE)
            if eval_raw is not None and not (isinstance(eval_raw, float) and pd.isna(eval_raw)):
                text = str(eval_raw).strip()
                if text:
                    eval_dates[key] = text

    try:
        lines, _warnings = load_gm_position_lines(valuation_date)
    except Exception:
        lines = []
    for line in lines:
        if line.kind == KIND_CASH:
            key = cash_instrument_id(line.broker_id)
        elif line.kind == KIND_POSITION and line.code:
            key = f"{line.broker_id}:{line.code}"
        else:
            continue
        fx = _implied_fx_pln(snapshot if snapshot is not None else pd.DataFrame(), line.broker_id, line.currency)
        terminals[key] = float(line.value) * float(fx)
        if line.evaluation_date:
            eval_dates[key] = str(line.evaluation_date)

    _fill_terminals_from_venue_roi(
        valuation_date,
        terminals,
        eval_dates,
        ledger=ledger,
    )
    return terminals, eval_dates


def _fill_terminals_from_venue_roi(
    valuation_date: date,
    terminals: dict[str, float],
    eval_dates: dict[str, str],
    *,
    ledger: pd.DataFrame | None,
) -> None:
    """Uzupełnia braki terminali z venue ROI (native → PLN) dla id z ledgera."""
    if ledger is None or ledger.empty:
        return
    needed = {
        str(iid)
        for iid in ledger[InstrumentCashFlow.INSTRUMENT_ID].astype(str).unique()
        if abs(float(terminals.get(str(iid), 0.0))) <= 1e-9
    }
    if not needed:
        return
    currency_by_id = _currency_by_instrument(ledger)
    for loader in _venue_roi_loaders():
        if not needed:
            break
        try:
            summary, *_rest = loader(valuation_date)
        except Exception:
            continue
        if summary is None or summary.empty:
            continue
        for _, row in summary.iterrows():
            key = str(row.get("asset_id") or "").strip()
            if key not in needed:
                continue
            native = pd.to_numeric(row.get("terminal_unrealized"), errors="coerce")
            if pd.isna(native) or abs(float(native)) <= 1e-9:
                continue
            currency = currency_by_id.get(key) or _guess_currency(key, row)
            try:
                converted = to_pln(float(native), currency, valuation_date)
            except Exception:
                continue
            terminals[key] = converted.amount_pln
            needed.discard(key)
            eval_raw = row.get(AssetsDef.EVALUATION_DATE)
            if eval_raw is not None and str(eval_raw).strip():
                eval_dates.setdefault(key, str(eval_raw).strip())


def _venue_roi_loaders():
    from roi.broker_obligacje_roi import compute_obligacje_broker_roi
    from roi.broker_trading_roi import compute_revolut_robo_ticker_roi
    from roi.compute_roi import compute_portfolio_roi
    from roi.degiro_roi import compute_degiro_ticker_roi
    from roi.mbank_deposit_roi import compute_mbank_deposit_roi
    from roi.revolut_deposit_roi import compute_revolut_deposit_roi
    from roi.xtb_roi import compute_xtb_ticker_roi

    def _catalog(vd: date):
        summary, _events = compute_portfolio_roi(vd)
        return summary, _events, []

    return (
        _catalog,
        compute_revolut_robo_ticker_roi,
        compute_degiro_ticker_roi,
        compute_xtb_ticker_roi,
        compute_obligacje_broker_roi,
        compute_revolut_deposit_roi,
        compute_mbank_deposit_roi,
    )


def _currency_by_instrument(ledger: pd.DataFrame | None) -> dict[str, str]:
    if ledger is None or ledger.empty:
        return {}
    out: dict[str, str] = {}
    for instrument_id, group in ledger.groupby(
        ledger[InstrumentCashFlow.INSTRUMENT_ID].astype(str)
    ):
        currencies = (
            group[InstrumentCashFlow.CURRENCY].astype(str).str.strip().str.upper()
        )
        currencies = currencies[currencies.ne("") & currencies.ne("NAN")]
        if currencies.empty:
            continue
        out[str(instrument_id)] = str(currencies.mode().iloc[0])
    return out


def _guess_currency(instrument_id: str, row: pd.Series) -> str:
    key = str(instrument_id)
    if key.startswith("p_degiro:") or key.startswith("p_re_robo:"):
        return "EUR"
    if key.startswith("p_re_eur") or key.startswith("g_re_eur"):
        return "EUR"
    if "currency" in row.index and str(row.get("currency") or "").strip():
        return str(row.get("currency")).strip().upper()
    return "PLN"


def _ledger_group_to_pln_events(instrument_id: str, group: pd.DataFrame) -> pd.DataFrame:
    """CashFlowEvent z AMOUNT = amount_pln (pod Razem / XIRR w PLN)."""
    rows: list[dict] = []
    for _, row in group.iterrows():
        rows.append(
            {
                CashFlowEvent.ASSET_ID: instrument_id,
                CashFlowEvent.DATE: row[InstrumentCashFlow.DATE],
                CashFlowEvent.AMOUNT: float(row[InstrumentCashFlow.AMOUNT_PLN]),
                CashFlowEvent.CATEGORY: str(row[InstrumentCashFlow.CATEGORY]),
                CashFlowEvent.SOURCE: str(row.get(InstrumentCashFlow.SOURCE) or ""),
                CashFlowEvent.DESCRIPTION: str(row.get(InstrumentCashFlow.DESCRIPTION) or ""),
                CashFlowEvent.TITLE: str(row.get(InstrumentCashFlow.TITLE) or ""),
                CashFlowEvent.COUNTERPARTY: str(row.get(InstrumentCashFlow.COUNTERPARTY) or ""),
                CashFlowEvent.ACCOUNT_NUMBER: str(
                    row.get(InstrumentCashFlow.ACCOUNT_NUMBER) or ""
                ),
            }
        )
    if not rows:
        return pd.DataFrame(columns=list(CashFlowEvent.COLUMN_ORDER))
    out = pd.DataFrame(rows, columns=list(CashFlowEvent.COLUMN_ORDER))
    CashFlowEvent.check_structure(out)
    return out


def _summary_row_from_pln_events(
    instrument_id: str,
    events: pd.DataFrame,
    valuation_date: date,
    *,
    terminal_unrealized: float,
    is_sold: bool,
    evaluation_date: str,
) -> dict:
    filtered = filter_excel_rows_on_or_before(events, CashFlowEvent.DATE, valuation_date)
    capex = _sum_category(filtered, CAPEX)
    opex = _sum_category(filtered, OPEX)
    revenue = _sum_category(filtered, REVENUES)
    terminal_realized = _sum_category(filtered, DIVESTMENT)
    flows_total = float(filtered[CashFlowEvent.AMOUNT].sum()) if not filtered.empty else 0.0
    terminal = 0.0 if is_sold else float(terminal_unrealized)
    roi_nominal = flows_total + terminal
    xirr_dates, xirr_amounts = cashflows_for_xirr(filtered, valuation_date, terminal)
    xirr = compute_xirr(xirr_dates, xirr_amounts)
    return roi_summary_to_row(
        RoiSummary(
            asset_id=instrument_id,
            capex=capex,
            opex=opex,
            revenue=revenue,
            terminal_realized=terminal_realized,
            terminal_unrealized=terminal,
            roi_nominal=roi_nominal,
            xirr=xirr,
            is_sold=is_sold,
            evaluation_date=evaluation_date or None,
        )
    )


def _sum_category(cashflows: pd.DataFrame, category: str) -> float:
    if cashflows.empty:
        return 0.0
    mask = cashflows[CashFlowEvent.CATEGORY] == category
    return float(cashflows.loc[mask, CashFlowEvent.AMOUNT].sum())


def _instrument_labels(ledger: pd.DataFrame) -> dict[str, str]:
    try:
        from importers.assets.instruments import InstrumentMapError, load_instrument_map

        mapping = load_instrument_map()
    except Exception:
        mapping = None

    labels: dict[str, str] = {}
    ids = ledger[InstrumentCashFlow.INSTRUMENT_ID].astype(str).unique()
    for instrument_id in ids:
        labels[instrument_id] = _label_for(instrument_id, mapping)
    return labels


def _label_for(instrument_id: str, mapping) -> str:
    key = str(instrument_id)
    if key.endswith(":CASH"):
        broker = key.rsplit(":", 1)[0]
        return f"Gotówka ({broker})"
    if mapping is None:
        return key
    try:
        if key.startswith("p_degiro:"):
            return mapping.instrument_for_degiro(key.split(":", 1)[1])
        if key.startswith("p_xtb:"):
            return mapping.instrument_for_xtb(key.split(":", 1)[1])
    except Exception:
        return key
    return key
