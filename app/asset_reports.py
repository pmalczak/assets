# -*- coding: utf-8 -*-
"""Raporty tekstowe uzywane przez main.py i app_assets.py."""

from __future__ import annotations

import pandas as pd
from pandas.io.formats.style import Styler

from importers.assets.data_model import AssetsDef
from portfolios.assignment import attach_portfolio_column

_SEPARATOR = "___________________\n"
_COL_SPACE = 15
_TOTAL = "Z RAZEM"
_CURRENCY_TOTAL = "RAZEM"
_RAZEM_PLN = "RAZEM-PLN"
_VALUE_PLN_EUR = f"{AssetsDef.VALUE_PLN}_eur".lower()
_VALUE_PLN_PLN = f"{AssetsDef.VALUE_PLN}_pln".lower()

# Kolory czcionek RAP (Streamlit / Styler) — portfele + waluty + sumy.
_PORTFOLIO_FONT_COLOR = {
    "0 OGÓLNY": "#1565C0",
    "1 REVOLUT-ROBO": "#6A1B9A",
    "2 G-MOMENTUM": "#2E7D32",
    _TOTAL: "#B71C1C",
}
_EUR_FONT_COLOR = "#1565C0"
_PLN_FONT_COLOR = "#AD1457"
_TOTAL_FONT_COLOR = "#B71C1C"


def _format_amount_columns(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for col in out.columns:
        out[col] = out[col].round().astype(int).map("{:,}".format).str.replace(",", " ")
    return out


def _as_multiindex(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy()
    if not isinstance(work.index, pd.MultiIndex):
        work.index = pd.MultiIndex.from_arrays(
            [work.index],
            names=[work.index.name or ""],
        )
    return work


def _blanked_index_labels(index: pd.Index) -> tuple[list[str], list[list[str]], list[tuple[str, ...]]]:
    """Etykiety indeksu jak w starym raporcie tekstowym: powtórzenia → pusty string.

    Zwraca: nazwy poziomów, wiersze z blankowaniem, pełne klucze (do stylowania).
    """
    if not isinstance(index, pd.MultiIndex):
        index = pd.MultiIndex.from_arrays([index], names=[index.name or ""])
    nlevels = index.nlevels
    index_names = ["" if name is None else str(name) for name in index.names]
    prev: list[str | None] = [None] * nlevels
    blanked_rows: list[list[str]] = []
    full_keys: list[tuple[str, ...]] = []
    for key in index:
        parts = key if isinstance(key, tuple) else (key,)
        full = tuple(str(part) for part in parts)
        full_keys.append(full)
        row: list[str] = []
        for i, text in enumerate(full):
            if text == prev[i]:
                row.append("")
            else:
                row.append(text)
                prev[i] = text
                for j in range(i + 1, nlevels):
                    prev[j] = None
        blanked_rows.append(row)
    return index_names, blanked_rows, full_keys


def format_rap_table(frame: pd.DataFrame, *, col_space: int = _COL_SPACE) -> str:
    """Tabela RAP: nagłówki i wartości w tych samych kolumnach, wyrównane do prawej."""
    if frame is None or frame.empty:
        return ""
    work = _as_multiindex(frame)
    index_names, index_rows, _full = _blanked_index_labels(work.index)
    nlevels = len(index_names)
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


def rap_display_frame(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str], list[tuple[str, ...]]]:
    """Ramka pod Streamlit: indeks → kolumny, powtórzone etykiety puste."""
    if frame is None or frame.empty:
        return pd.DataFrame(), [], []
    work = _as_multiindex(frame)
    index_names, blanked_rows, full_keys = _blanked_index_labels(work.index)
    label_cols = [name if name else f"level_{i}" for i, name in enumerate(index_names)]
    display = work.reset_index(drop=True)
    for i, col in enumerate(label_cols):
        display.insert(i, col, [row[i] for row in blanked_rows])
    return display, label_cols, full_keys


def _is_total_label(value: object) -> bool:
    return str(value) == _TOTAL


def _column_font_color(col: object) -> str | None:
    name = str(col)
    if name in (_CURRENCY_TOTAL, _RAZEM_PLN, "RAZEM"):
        return _TOTAL_FONT_COLOR
    lower = name.lower()
    if name == "EUR" or lower.endswith("_eur"):
        return _EUR_FONT_COLOR
    if name == "PLN" or lower.endswith("_pln"):
        return _PLN_FONT_COLOR
    return None


def style_rap_table(frame: pd.DataFrame) -> Styler:
    """Pandas Styler pod Streamlit: blankowane etykiety + kolory portfeli/walut/sum."""
    display, label_cols, full_keys = rap_display_frame(frame)
    if display.empty:
        return pd.DataFrame().style

    label_set = set(label_cols)
    styler = display.style.set_properties(
        **{"font-family": "ui-monospace, monospace"}
    )

    def _row_css(row: pd.Series) -> list[str]:
        parts = full_keys[int(row.name)]
        is_total_row = any(_is_total_label(p) for p in parts)
        styles: list[str] = []
        for col in row.index:
            bits: list[str] = []
            if col in label_set:
                bits.append("text-align: left")
                text = str(row[col]) if row[col] is not None else ""
                if text:
                    if col == label_cols[0]:
                        color = _PORTFOLIO_FONT_COLOR.get(text)
                        if color:
                            bits.append(f"color: {color}")
                            bits.append("font-weight: 600" if not _is_total_label(text) else "font-weight: 700")
                    elif _is_total_label(text):
                        bits.append(f"color: {_TOTAL_FONT_COLOR}")
                        bits.append("font-weight: 700")
            else:
                bits.append("text-align: right")
                col_color = _column_font_color(col)
                if col_color:
                    bits.append(f"color: {col_color}")
                if is_total_row or col_color == _TOTAL_FONT_COLOR:
                    bits.append("font-weight: 700")
            if is_total_row and col in label_set and str(row[col]):
                bits.append("font-weight: 700")
            styles.append("; ".join(bits))
        return styles

    return styler.apply(_row_css, axis=1)


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
    work = attach_portfolio_column(assets)
    a1 = work[
        [AssetsDef.PORTFOLIO, AssetsDef.GROUP, AssetsDef.CURRENCY, AssetsDef.VALUE_PLN]
    ].copy()
    a1[AssetsDef.VALUE_PLN] = pd.to_numeric(a1[AssetsDef.VALUE_PLN], errors="coerce").fillna(0)

    a_group_total = a1.copy()
    a_group_total[AssetsDef.GROUP] = _TOTAL
    a_currency_total = a1.copy()
    a_currency_total[AssetsDef.CURRENCY] = _CURRENCY_TOTAL
    a_both = a_currency_total.copy()
    a_both[AssetsDef.GROUP] = _TOTAL

    a_all = a1.copy()
    a_all[AssetsDef.PORTFOLIO] = _TOTAL
    a_all_group = a_group_total.copy()
    a_all_group[AssetsDef.PORTFOLIO] = _TOTAL
    a_all_currency = a_currency_total.copy()
    a_all_currency[AssetsDef.PORTFOLIO] = _TOTAL
    a_all_both = a_both.copy()
    a_all_both[AssetsDef.PORTFOLIO] = _TOTAL

    df = pd.concat(
        [
            a1,
            a_group_total,
            a_currency_total,
            a_both,
            a_all,
            a_all_group,
            a_all_currency,
            a_all_both,
        ]
    )
    g1 = df.groupby([AssetsDef.PORTFOLIO, AssetsDef.GROUP, AssetsDef.CURRENCY]).sum()
    g1 = g1.unstack(AssetsDef.CURRENCY).fillna(0)
    g1.columns = g1.columns.get_level_values(1)
    return _format_amount_columns(g1)
