# -*- coding: utf-8 -*-
"""Raporty tekstowe uzywane przez main.py i app_assets.py."""

from __future__ import annotations

import pandas as pd

from importers.assets.data_model import AssetsDef
from portfolios.assignment import KNOWN_PORTFOLIOS, attach_portfolio_column

_SEPARATOR = "___________________\n"
_COL_SPACE = 15
_TOTAL = "Z RAZEM"
_RAZEM_PLN = "RAZEM-PLN"
_RAZEM = "RAZEM"
_SHARE = "udział"
_VALUE_PLN_EUR = f"{AssetsDef.VALUE_PLN}_eur".lower()
_VALUE_PLN_PLN = f"{AssetsDef.VALUE_PLN}_pln".lower()


def _format_amount_columns(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for col in out.columns:
        out[col] = out[col].round().astype(int).map("{:,}".format).str.replace(",", " ")
    return out


def format_rap_table(frame: pd.DataFrame, *, col_space: int = _COL_SPACE) -> str:
    """Tabela RAP: nagłówki i wartości w tych samych kolumnach, wyrównane do prawej."""
    if frame is None or frame.empty:
        return ""
    work = frame.copy()
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
    columns_name = "" if work.columns.name is None else str(work.columns.name)
    header = (columns_name.ljust(index_block) if columns_name else " " * index_block)
    header += "".join(name.rjust(width) for name, width in zip(col_names, col_widths))
    names_line = "".join(name.ljust(width) for name, width in zip(index_names, index_widths))
    names_line += " " * sum(col_widths)
    lines = [header, names_line]
    for index_row, values in zip(index_rows, value_rows):
        line = "".join(label.ljust(width) for label, width in zip(index_row, index_widths))
        line += "".join(value.rjust(width) for value, width in zip(values, col_widths))
        lines.append(line)
    return "\n".join(lines)


def rap2(assets: pd.DataFrame) -> pd.DataFrame:
    work = attach_portfolio_column(assets)
    a1 = work[
        [
            AssetsDef.PORTFOLIO,
            AssetsDef.TYPE,
            AssetsDef.VALUE,
            AssetsDef.VALUE_PLN,
            AssetsDef.CURRENCY,
        ]
    ].copy()
    for col in (AssetsDef.VALUE, AssetsDef.VALUE_PLN):
        a1[col] = pd.to_numeric(a1[col], errors="coerce").fillna(0)

    a_type_total = a1.copy()
    a_type_total[AssetsDef.TYPE] = _TOTAL
    a_all_portfolios = a1.copy()
    a_all_portfolios[AssetsDef.PORTFOLIO] = _TOTAL
    a_grand = a_type_total.copy()
    a_grand[AssetsDef.PORTFOLIO] = _TOTAL

    a1 = pd.concat([a1, a_type_total, a_all_portfolios, a_grand])
    g1 = a1.groupby([AssetsDef.PORTFOLIO, AssetsDef.TYPE, AssetsDef.CURRENCY]).sum()
    g1 = g1.unstack(AssetsDef.CURRENCY).fillna(0)
    g1.columns = [f"{col}_{cur}".lower() for col, cur in g1.columns]
    pln_eur = g1[_VALUE_PLN_EUR] if _VALUE_PLN_EUR in g1.columns else 0
    pln_pln = g1[_VALUE_PLN_PLN] if _VALUE_PLN_PLN in g1.columns else 0
    g1[_RAZEM_PLN] = pln_eur + pln_pln
    g1 = _format_amount_columns(g1)
    return g1


def rap1(assets: pd.DataFrame) -> pd.DataFrame:
    """Jeden wiersz na portfel: RAZEM (PLN) + udział % w sumie wszystkich portfeli."""
    work = attach_portfolio_column(assets)
    empty = pd.DataFrame(columns=[_RAZEM, _SHARE])
    empty.index.name = AssetsDef.PORTFOLIO
    if work is None or work.empty or AssetsDef.VALUE_PLN not in work.columns:
        return empty

    a1 = work[[AssetsDef.PORTFOLIO, AssetsDef.VALUE_PLN]].copy()
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
    total = float(by_portfolio.sum())
    share = (by_portfolio / total * 100.0) if total else by_portfolio * 0.0

    out = pd.DataFrame({_RAZEM: by_portfolio, _SHARE: share})
    out.loc[_TOTAL] = {_RAZEM: total, _SHARE: 100.0 if total else 0.0}
    out.index.name = AssetsDef.PORTFOLIO

    formatted = out.copy()
    formatted[_RAZEM] = (
        formatted[_RAZEM].round().astype(int).map("{:,}".format).str.replace(",", " ")
    )
    formatted[_SHARE] = formatted[_SHARE].map(lambda value: f"{float(value):.1f}%")
    return formatted
