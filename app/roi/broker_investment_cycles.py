# -*- coding: utf-8 -*-
"""Cykle ekspozycji brokerów udziałowych: pełne spłaszczenie qty → osobny instrument_id.

Otwarty (ostatni) cykl zachowuje goły ``{broker}:{code}``.
Zamknięty: ``{broker}:{code}#{YYYY-MM-DD}`` (data zejścia qty≈0).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from roi.categories import CAPEX, DIVESTMENT
from roi.data_model import CashFlowEvent

QTY_EPS = 1e-12
CYCLE_ID_SEP = "#"


def broker_base_instrument_id(instrument_id: str | None) -> str:
    """``p_degiro:ISIN#2026-08-31`` → ``p_degiro:ISIN``."""
    key = str(instrument_id or "").strip()
    if not key:
        return ""
    return key.split(CYCLE_ID_SEP, 1)[0]


def broker_code_from_instrument_id(instrument_id: str | None) -> str:
    """Kod ISIN/ticker z id (z lub bez sufiksu cyklu)."""
    base = broker_base_instrument_id(instrument_id)
    if ":" not in base:
        return base
    return base.split(":", 1)[1]


def is_closed_cycle_instrument_id(instrument_id: str | None) -> bool:
    return CYCLE_ID_SEP in str(instrument_id or "")


def closed_cycle_instrument_id(base_id: str, close_date: date, *, collision: int = 1) -> str:
    stamp = close_date.isoformat()
    if collision <= 1:
        return f"{base_id}{CYCLE_ID_SEP}{stamp}"
    return f"{base_id}{CYCLE_ID_SEP}{stamp}.{collision}"


def closed_cycle_label_suffix(instrument_id: str | None) -> str:
    """Fragment UI `` (zamk. YYYY-MM-DD)`` albo pusty."""
    key = str(instrument_id or "")
    if CYCLE_ID_SEP not in key:
        return ""
    stamp = key.split(CYCLE_ID_SEP, 1)[1]
    day = stamp.split(".", 1)[0]
    return f" (zamk. {day})"


@dataclass(frozen=True)
class _CycleBuf:
    rows: list[dict]
    close_date: date | None  # None = nadal otwarty na końcu serii


def partition_broker_cashflows(
    events_by_asset: dict[str, pd.DataFrame],
    *,
    skip_codes: frozenset[str] | None = None,
) -> tuple[dict[str, pd.DataFrame], list[str]]:
    """Podziel CF per papier na cykle ekspozycji.

    ``skip_codes`` — same kody po ``:`` (np. ``REVOLUT-ROBO``), bez partycji.
    Brak qty przy CAPEX/DIVESTMENT → warning i jeden cykl (goły id).
    """
    if not events_by_asset:
        return {}, []
    skip = skip_codes or frozenset()
    out: dict[str, pd.DataFrame] = {}
    warnings: list[str] = []
    for asset_id, events in sorted(events_by_asset.items()):
        code = broker_code_from_instrument_id(asset_id)
        if code in skip:
            out[str(asset_id)] = events.copy() if events is not None else events
            continue
        if events is None or events.empty:
            out[str(asset_id)] = (
                events.copy()
                if events is not None
                else pd.DataFrame(columns=list(CashFlowEvent.COLUMN_ORDER))
            )
            continue
        partitioned, w = _partition_one_asset(str(asset_id), events)
        warnings.extend(w)
        out.update(partitioned)
    return out, warnings


def _partition_one_asset(
    base_id: str, events: pd.DataFrame
) -> tuple[dict[str, pd.DataFrame], list[str]]:
    work = events.copy()
    work["_sort_date"] = pd.to_datetime(work[CashFlowEvent.DATE], errors="coerce")
    work = work.sort_values("_sort_date", kind="mergesort").reset_index(drop=True)

    trade_cats = {
        str(c)
        for c in work[CashFlowEvent.CATEGORY].tolist()
        if str(c) in (CAPEX, DIVESTMENT)
    }
    missing_qty_cat: str | None = None
    for _, row in work.iterrows():
        cat = str(row.get(CashFlowEvent.CATEGORY) or "")
        if cat not in (CAPEX, DIVESTMENT):
            continue
        qty = row.get(CashFlowEvent.QUANTITY)
        if qty is None or (isinstance(qty, float) and pd.isna(qty)) or abs(float(qty)) <= QTY_EPS:
            missing_qty_cat = cat
            break
    if missing_qty_cat is not None:
        frame = _frame_from_rows(work.drop(columns=["_sort_date"], errors="ignore"))
        # Warning tylko gdy mogłyby powstać 2+ cykle (jest i kupno, i sprzedaż).
        if CAPEX in trade_cats and DIVESTMENT in trade_cats:
            return (
                {base_id: frame},
                [
                    f"{base_id}: brak quantity przy {missing_qty_cat} "
                    "— bez podziału na cykle ekspozycji"
                ],
            )
        return {base_id: frame}, []

    cycles: list[_CycleBuf] = []
    current: list[dict] = []
    qty = 0.0
    was_open = False

    for _, row in work.iterrows():
        record = {
            col: row[col]
            for col in CashFlowEvent.COLUMN_ORDER
            if col in work.columns
        }
        cat = str(record.get(CashFlowEvent.CATEGORY) or "")
        if cat in (CAPEX, DIVESTMENT):
            q = abs(float(record.get(CashFlowEvent.QUANTITY) or 0.0))
            signed = q if cat == CAPEX else -q
            qty += signed
            current.append(record)
            if abs(qty) > QTY_EPS:
                was_open = True
            elif was_open:
                close_day = _row_date(record)
                cycles.append(_CycleBuf(rows=current, close_date=close_day))
                current = []
                was_open = False
                qty = 0.0
            continue

        # REVENUES / OPEX / inne — do bieżącego bufora; gdy flat, do ostatniego zamkniętego.
        if current or was_open or abs(qty) > QTY_EPS:
            current.append(record)
        elif cycles:
            cycles[-1].rows.append(record)
        else:
            current.append(record)

    if current:
        # Ostatni bufor = cykl otwarty (goły id) albo osierocone CF przed pierwszym trade.
        cycles.append(_CycleBuf(rows=current, close_date=None))

    return _emit_cycles(base_id, cycles), []


def _emit_cycles(base_id: str, cycles: list[_CycleBuf]) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    close_counts: dict[str, int] = {}
    for buf in cycles:
        if buf.close_date is None:
            cycle_id = base_id
        else:
            key = buf.close_date.isoformat()
            close_counts[key] = close_counts.get(key, 0) + 1
            cycle_id = closed_cycle_instrument_id(
                base_id, buf.close_date, collision=close_counts[key]
            )
        frame = _frame_from_rows(buf.rows)
        frame[CashFlowEvent.ASSET_ID] = cycle_id
        out[cycle_id] = frame
    return out


def _frame_from_rows(rows: list[dict] | pd.DataFrame) -> pd.DataFrame:
    if isinstance(rows, pd.DataFrame):
        cols = [c for c in CashFlowEvent.COLUMN_ORDER if c in rows.columns]
        out = rows.loc[:, cols].copy()
        for col in CashFlowEvent.COLUMN_ORDER:
            if col not in out.columns:
                out[col] = None if col in (CashFlowEvent.QUANTITY, CashFlowEvent.UNIT_PRICE) else ""
        out = out[list(CashFlowEvent.COLUMN_ORDER)]
        CashFlowEvent.check_structure(out)
        return out
    if not rows:
        return pd.DataFrame(columns=list(CashFlowEvent.COLUMN_ORDER))
    out = pd.DataFrame(rows, columns=list(CashFlowEvent.COLUMN_ORDER))
    CashFlowEvent.check_structure(out)
    return out


def _row_date(record: dict) -> date:
    raw = record.get(CashFlowEvent.DATE)
    ts = pd.to_datetime(raw, errors="coerce")
    if pd.isna(ts):
        raise ValueError(f"Brak daty CF w cyklu: {raw!r}")
    return ts.date()
