# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from data_step.data_step import DATA_STEP
from nbp_fx_repo.nbp_fx_repository import NBP_API_EUR, NbpFxRepository

FX_MIN_YEAR = 2005
CHART_MONTHS = 6
DATE_COL = "date"
RATE_COL = "eur_pln"


def _fx_cache_directory() -> Path:
    metadata_root: Path = DATA_STEP.metadata.get_metadata_root() / "fx"
    metadata_root.mkdir(parents=True, exist_ok=True)
    return metadata_root


@st.cache_data(show_spinner=False)
def _load_eur_fx_history() -> pd.DataFrame:
    fx_repo = NbpFxRepository(target_directory=_fx_cache_directory(), min_year=FX_MIN_YEAR)
    fx_rates = fx_repo.update_to_date()
    if NBP_API_EUR not in fx_rates.columns:
        return pd.DataFrame(columns=[DATE_COL, RATE_COL])

    series = fx_rates[[NBP_API_EUR]].copy()
    series = series.reset_index()
    date_col = series.columns[0]
    series = series.rename(columns={date_col: DATE_COL, NBP_API_EUR: RATE_COL})
    series[DATE_COL] = pd.to_datetime(series[DATE_COL], errors="coerce")
    series[RATE_COL] = pd.to_numeric(series[RATE_COL], errors="coerce")
    series = series.dropna(subset=[DATE_COL, RATE_COL]).sort_values(DATE_COL)
    return series.reset_index(drop=True)


def _last_months(history: pd.DataFrame, months: int) -> pd.DataFrame:
    end = pd.Timestamp(history[DATE_COL].max()).normalize()
    start = end - pd.DateOffset(months=months)
    return history[history[DATE_COL] >= start].copy()


def render_fx() -> None:
    st.subheader("FX — historia EUR/PLN (NBP)")

    try:
        with st.spinner("Ladowanie kursow NBP..."):
            history = _load_eur_fx_history()
    except Exception as exc:
        st.error("Nie udalo sie wczytac historii FX.")
        st.exception(exc)
        return

    if history.empty:
        st.warning("Brak danych FX w cache NBP.")
        return

    chart_history = _last_months(history, CHART_MONTHS)
    if chart_history.empty:
        st.warning(f"Brak notowan EUR z ostatnich {CHART_MONTHS} miesiecy.")
        return

    latest = chart_history.iloc[-1]
    first = chart_history.iloc[0]
    latest_rate = float(latest[RATE_COL])
    first_rate = float(first[RATE_COL])
    delta = latest_rate - first_rate
    delta_pct = (delta / first_rate * 100) if first_rate else 0.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ostatni kurs EUR", f"{latest_rate:.4f} PLN")
    c2.metric("Data ostatniego kursu", pd.Timestamp(latest[DATE_COL]).date().isoformat())
    c3.metric(f"Zmiana ({CHART_MONTHS} mies.)", f"{delta:+.4f} PLN", f"{delta_pct:+.1f}%")
    c4.metric("Notowania w oknie", f"{len(chart_history):,}".replace(",", " "))

    st.caption(
        f"Wykres: ostatnie {CHART_MONTHS} miesiecy. "
        f"Zrodlo: NBP tabela A, cache `{_fx_cache_directory()}`"
    )

    month_starts = pd.date_range(
        chart_history[DATE_COL].min().normalize(),
        chart_history[DATE_COL].max().normalize(),
        freq="MS",
    )
    # Pionowe linie na granicach miesiecy wewnatrz okna (bez pierwszej daty okna).
    month_lines = pd.DataFrame(
        {DATE_COL: [ts for ts in month_starts if ts > chart_history[DATE_COL].min().normalize()]}
    )

    line_chart = (
        alt.Chart(chart_history)
        .mark_line()
        .encode(
            x=alt.X(f"{DATE_COL}:T", title="Data"),
            y=alt.Y(f"{RATE_COL}:Q", title="EUR/PLN", scale=alt.Scale(zero=False)),
            tooltip=[
                alt.Tooltip(f"{DATE_COL}:T", title="Data"),
                alt.Tooltip(f"{RATE_COL}:Q", title="EUR/PLN", format=".4f"),
            ],
        )
    )
    layers = [line_chart]
    if not month_lines.empty:
        month_rules = (
            alt.Chart(month_lines)
            .mark_rule(color="#666666", strokeWidth=1, opacity=0.45)
            .encode(x=f"{DATE_COL}:T")
        )
        layers = [month_rules, line_chart]
    st.altair_chart(alt.layer(*layers), width="stretch")

    with st.expander("Tabela kursow EUR/PLN (okno wykresu)", expanded=False):
        display = chart_history.copy()
        display[DATE_COL] = display[DATE_COL].dt.strftime("%Y-%m-%d")
        display = display.rename(columns={DATE_COL: "Data", RATE_COL: "EUR/PLN"})
        st.dataframe(display.iloc[::-1], width="stretch", hide_index=True, height=420)
