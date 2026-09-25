# -*- coding: utf-8 -*-
"""Eksport ledgeru CF w perspektywie nazwanego portfela."""
from __future__ import annotations

import io
import re
from datetime import date

import pandas as pd

from portfolio_cf.allocate import allocate_ledger_to_portfolio
from portfolio_cf.assemble import AssemblyResult
from portfolio_cf.coverage import CoverageStatus
from portfolio_cf.data_model import InstrumentCashFlow
from portfolio_cf.instrument_portfolio import portfolio_for_instrument
from portfolio_cf.sold_status import (
    filter_coverage_by_sold,
    filter_ledger_by_sold,
    is_instrument_sold,
    sold_filter_label,
)


def portfolio_cf_excel_filename(portfolio_name: str, valuation_date: date) -> str:
    slug = _slug_portfolio(portfolio_name)
    return f"portfolio_cf_{slug}_{valuation_date:%Y-%m-%d}.xlsx"


def portfolio_cf_to_excel_bytes(
    assembly: AssemblyResult,
    portfolio_name: str,
    valuation_date: date,
    *,
    sold_filter: str | None = None,
) -> bytes:
    """XLSX: arkusz `cf` (ledger portfela), `coverage`, `meta` — po filtrze sprzedane."""
    mode = sold_filter if sold_filter is not None else sold_filter_label()
    cf = allocate_ledger_to_portfolio(assembly.ledger, portfolio_name)
    cf = filter_ledger_by_sold(
        cf, assembly.is_sold_by_instrument, sold_filter=mode
    ).copy()
    if not cf.empty:
        cf.insert(0, "portfel", portfolio_name)
        cf[InstrumentCashFlow.DATE] = (
            pd.to_datetime(cf[InstrumentCashFlow.DATE], errors="coerce")
            .dt.strftime("%Y-%m-%d")
        )
        cf = cf.sort_values(
            [InstrumentCashFlow.DATE, InstrumentCashFlow.INSTRUMENT_ID],
            ascending=[False, True],
        ).reset_index(drop=True)

    coverage_items = filter_coverage_by_sold(
        assembly.coverage,
        assembly.is_sold_by_instrument,
        portfolio_name=portfolio_name,
        sold_filter=mode,
    )
    coverage_rows = []
    for item in coverage_items:
        if item.status == CoverageStatus.EXCLUDED:
            continue
        coverage_rows.append(
            {
                "portfel": portfolio_name,
                "instrument_id": item.instrument_id,
                "status": item.status.value,
                "is_sold": is_instrument_sold(
                    item.instrument_id, assembly.is_sold_by_instrument
                ),
                "reason": item.reason,
                "venue": item.venue,
            }
        )
    coverage = pd.DataFrame(coverage_rows)
    if not coverage.empty:
        coverage = coverage.sort_values("instrument_id").reset_index(drop=True)

    meta = pd.DataFrame(
        [
            {"key": "portfel", "value": portfolio_name},
            {"key": "data_obliczenia", "value": valuation_date.isoformat()},
            {"key": "filtr_pozycji", "value": mode},
            {"key": "cf_rows", "value": str(len(cf))},
            {"key": "coverage_rows", "value": str(len(coverage))},
            {
                "key": "uncovered",
                "value": ", ".join(
                    item.instrument_id
                    for item in coverage_items
                    if item.status == CoverageStatus.UNCOVERED
                ),
            },
        ]
    )

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        cf.to_excel(writer, sheet_name="cf", index=False)
        coverage.to_excel(writer, sheet_name="coverage", index=False)
        meta.to_excel(writer, sheet_name="meta", index=False)
    return buffer.getvalue()


def _slug_portfolio(portfolio_name: str) -> str:
    text = str(portfolio_name).strip().lower()
    text = (
        text.replace("ł", "l")
        .replace("ą", "a")
        .replace("ę", "e")
        .replace("ó", "o")
        .replace("ś", "s")
        .replace("ć", "c")
        .replace("ń", "n")
        .replace("ź", "z")
        .replace("ż", "z")
    )
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "portfel"
