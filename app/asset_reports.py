# -*- coding: utf-8 -*-
"""Raporty tekstowe używane przez app_assets.py."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

import pandas as pd

from importers.assets.data_model import AssetsDef
from nbp_fx_repo.nbp_fx_repository import NBP_API_EUR
from portfolio_cf.fx_attribution import (
    FX_NAV_SHOCK_ABS,
    eur_nav_delta_pln,
    format_fx_t_eur_label,
)
from portfolios.assignment import KNOWN_PORTFOLIOS, attach_portfolio_column

_COL_SPACE = 15
_TOTAL = "Z RAZEM"
_RAZEM = "RAZEM"
_SHARE = "udział"
_NAV_FX = f"ΔNAV +{FX_NAV_SHOCK_ABS:g}"
_XIRR = "XIRR"
_XIRR_PLN = "XIRR PLN"


def format_rap_table(frame: pd.DataFrame, *, col_space: int = _COL_SPACE) -> str:
    """Tabela RAP: nagłówki i wartości w tych samych kolumnach, wyrównane do prawej.

    ``columns.name`` (np. etykieta FX_T) idzie jako osobna linia nad tabelą —
    nie w bloku indeksu, żeby nie psuć wyrównania kolumn.
    """
    if frame is None or frame.empty:
        return ""
    work = frame.copy()
    banner = "" if work.columns.name is None else str(work.columns.name).strip()
    work.columns.name = None
    if not isinstance(work.index, pd.MultiIndex):
        work.index = pd.MultiIndex.from_arrays(
            [work.index],
            names=[work.index.name or ""],
        )
    nlevels = work.index.nlevels
    index_names = ["" if name is None else str(name) for name in work.index.names]
    prev: list[str | None] = [None] * nlevels
    index_rows: list[list[str]] = []
    for key in work.index:
        parts = key if isinstance(key, tuple) else (key,)
        row: list[str] = []
        for i, part in enumerate(parts):
            text = str(part)
            if text == prev[i]:
                row.append("")
            else:
                row.append(text)
                prev[i] = text
                for j in range(i + 1, nlevels):
                    prev[j] = None
        index_rows.append(row)
    index_widths = []
    for i in range(nlevels):
        widest = max([len(index_names[i])] + [len(row[i]) for row in index_rows])
        index_widths.append(max(col_space, widest))
    col_names = [str(col) for col in work.columns]
    value_rows = [[str(v) for v in row] for row in work.itertuples(index=False, name=None)]
    col_widths = []
    for i, name in enumerate(col_names):
        widest_value = max((len(row[i]) for row in value_rows), default=0)
        col_widths.append(max(col_space, len(name) + 1, widest_value))
    index_block = sum(index_widths)
    header = " " * index_block
    header += "".join(name.rjust(width) for name, width in zip(col_names, col_widths))
    names_line = "".join(name.ljust(width) for name, width in zip(index_names, index_widths))
    names_line += " " * sum(col_widths)
    lines = [header, names_line]
    for index_row, values in zip(index_rows, value_rows):
        line = "".join(label.ljust(width) for label, width in zip(index_row, index_widths))
        line += "".join(value.rjust(width) for value, width in zip(values, col_widths))
        lines.append(line)
    body = "\n".join(lines)
    return f"{banner}\n{body}" if banner else body


def format_xirr_cell(value: float | None) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    return f"{float(value) * 100:.1f}%"


def rap1(
    assets: pd.DataFrame,
    *,
    xirr_by_portfolio: Mapping[str, float | None] | None = None,
    xirr_pln_by_portfolio: Mapping[str, float | None] | None = None,
    valuation_date: date | None = None,
    fx_rates: pd.DataFrame | None = None,
    fx_t_label: str | None = None,
    fx_shock_abs: float = FX_NAV_SHOCK_ABS,
) -> pd.DataFrame:
    """Jeden wiersz na portfel: RAZEM + udział + ΔNAV przy FX+shock + XIRR lokalny/PLN.

    ``ΔNAV +0.1`` = Σ wartość_EUR × 0.1 (bezwzględny ruch kursu, nie %).
    ``fx_t_label`` / ``valuation_date`` → ``columns.name`` = etykieta FX_T EUR.
    """
    work = attach_portfolio_column(assets)
    empty = pd.DataFrame(columns=[_RAZEM, _SHARE, _NAV_FX, _XIRR, _XIRR_PLN])
    empty.index.name = AssetsDef.PORTFOLIO
    label = _resolve_fx_t_label(
        fx_t_label=fx_t_label,
        valuation_date=valuation_date,
        fx_rates=fx_rates,
    )
    if label:
        empty.columns.name = label
    if work is None or work.empty or AssetsDef.VALUE_PLN not in work.columns:
        return empty

    cols = [AssetsDef.PORTFOLIO, AssetsDef.VALUE_PLN]
    if AssetsDef.VALUE in work.columns:
        cols.append(AssetsDef.VALUE)
    if AssetsDef.CURRENCY in work.columns:
        cols.append(AssetsDef.CURRENCY)
    a1 = work[cols].copy()
    a1[AssetsDef.VALUE_PLN] = pd.to_numeric(a1[AssetsDef.VALUE_PLN], errors="coerce").fillna(0)
    has_portfolio = a1[AssetsDef.PORTFOLIO].astype(str).str.strip().ne("")
    a1 = a1.loc[has_portfolio]
    if a1.empty:
        return empty

    by_portfolio = (
        a1.groupby(AssetsDef.PORTFOLIO, dropna=False)[AssetsDef.VALUE_PLN]
        .sum()
        .reindex(list(KNOWN_PORTFOLIOS), fill_value=0)
    )
    nav_fx = _nav_fx_sensitivity_by_portfolio(a1, shock_abs=fx_shock_abs)
    total = float(by_portfolio.sum())
    share = (by_portfolio / total * 100.0) if total else by_portfolio * 0.0
    xirr_map = dict(xirr_by_portfolio or {})
    xirr_pln_map = dict(xirr_pln_by_portfolio or {})
    xirr_series = pd.Series(
        {name: xirr_map.get(name) for name in by_portfolio.index},
        dtype=object,
    )
    xirr_pln_series = pd.Series(
        {name: xirr_pln_map.get(name) for name in by_portfolio.index},
        dtype=object,
    )

    out = pd.DataFrame(
        {
            _RAZEM: by_portfolio,
            _SHARE: share,
            _NAV_FX: nav_fx,
            _XIRR: xirr_series,
            _XIRR_PLN: xirr_pln_series,
        }
    )
    out.loc[_TOTAL] = {
        _RAZEM: total,
        _SHARE: 100.0 if total else 0.0,
        _NAV_FX: float(nav_fx.sum()),
        _XIRR: xirr_map.get(_TOTAL),
        _XIRR_PLN: xirr_pln_map.get(_TOTAL),
    }
    out.index.name = AssetsDef.PORTFOLIO

    formatted = out.copy()
    formatted[_RAZEM] = (
        formatted[_RAZEM].round().astype(int).map("{:,}".format).str.replace(",", " ")
    )
    formatted[_SHARE] = formatted[_SHARE].map(lambda value: f"{float(value):.1f}%")
    formatted[_NAV_FX] = (
        formatted[_NAV_FX].round().astype(int).map("{:,}".format).str.replace(",", " ")
    )
    formatted[_XIRR] = formatted[_XIRR].map(format_xirr_cell)
    formatted[_XIRR_PLN] = formatted[_XIRR_PLN].map(format_xirr_cell)
    if label:
        formatted.columns.name = label
    return formatted


def _nav_fx_sensitivity_by_portfolio(
    frame: pd.DataFrame,
    *,
    shock_abs: float,
) -> pd.Series:
    """ΔNAV_PLN per portfel przy EUR/PLN += shock_abs; pozycje nie-EUR → 0."""
    zero = pd.Series(0.0, index=list(KNOWN_PORTFOLIOS), dtype=float)
    if AssetsDef.VALUE not in frame.columns or AssetsDef.CURRENCY not in frame.columns:
        return zero
    native = pd.to_numeric(frame[AssetsDef.VALUE], errors="coerce").fillna(0.0)
    currency = frame[AssetsDef.CURRENCY].astype(str).str.strip().str.upper()
    delta = pd.Series(0.0, index=frame.index, dtype=float)
    eur_mask = currency.eq(NBP_API_EUR)
    delta.loc[eur_mask] = native.loc[eur_mask].map(
        lambda value: eur_nav_delta_pln(value, shock_abs=shock_abs)
    )
    return (
        delta.groupby(frame[AssetsDef.PORTFOLIO], dropna=False)
        .sum()
        .reindex(list(KNOWN_PORTFOLIOS), fill_value=0.0)
    )


def _resolve_fx_t_label(
    *,
    fx_t_label: str | None,
    valuation_date: date | None,
    fx_rates: pd.DataFrame | None,
) -> str | None:
    if fx_t_label is not None:
        text = str(fx_t_label).strip()
        return text or None
    if valuation_date is None:
        return None
    return format_fx_t_eur_label(valuation_date, fx_rates=fx_rates)
