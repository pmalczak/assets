# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

from app_proc.data_steps_root import get_nbp_fx_cache_dir
from nbp_fx_repo.nbp_fx_repository import NBP_API_EUR, NbpFxRepository
from nbp_pl_api.nbp_gold_fetch import NBP_GOLD_DATE, NBP_GOLD_PRICE, fetch_nbp_gold
from roi.gold_terminal import TROY_OUNCE_GRAMS

FX_MIN_YEAR = 2005
CHART_MONTHS = 6
DATE_COL = "date"
RATE_COL = "eur_pln"
GOLD_COL = "zloto_pln_oz"
GOLD_UNIT = "PLN/oz"
EUR_COLOR = "#4C78A8"
GOLD_COLOR = "#E6A817"
CHART_HEIGHT = 380


def _pln_oz(value: float, *, signed: bool = False) -> str:
    number = f"{value:+,.2f}" if signed else f"{value:,.2f}"
    return f"{number.replace(',', ' ')} {GOLD_UNIT}"


@st.cache_data(show_spinner=False)
def _load_eur_fx_history() -> pd.DataFrame:
    fx_repo = NbpFxRepository(target_directory=get_nbp_fx_cache_dir(), min_year=FX_MIN_YEAR)
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


@st.cache_data(show_spinner=False)
def _load_gold_window(start: str, end: str) -> pd.DataFrame:
    """Cena złota NBP w oknie wykresu, PLN za uncję trojańską. Nie cena monet."""
    series = fetch_nbp_gold(date.fromisoformat(start), date.fromisoformat(end))
    if series.empty:
        return pd.DataFrame(columns=[DATE_COL, GOLD_COL])

    out = series.rename(columns={NBP_GOLD_DATE: DATE_COL, NBP_GOLD_PRICE: GOLD_COL})
    out[DATE_COL] = pd.to_datetime(out[DATE_COL], errors="coerce")
    out[GOLD_COL] = pd.to_numeric(out[GOLD_COL], errors="coerce") * TROY_OUNCE_GRAMS
    out = out.dropna(subset=[DATE_COL, GOLD_COL]).sort_values(DATE_COL)
    return out.reset_index(drop=True)


def _window(history: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if history.empty:
        return history.copy()
    mask = (history[DATE_COL] >= start) & (history[DATE_COL] <= end)
    return history.loc[mask].copy()


def _last_months(history: pd.DataFrame, months: int) -> pd.DataFrame:
    end = pd.Timestamp(history[DATE_COL].max()).normalize()
    start = end - pd.DateOffset(months=months)
    return history[history[DATE_COL] >= start].copy()


def build_fx_chart(
    eur: pd.DataFrame,
    gold: pd.DataFrame,
    month_lines: pd.DataFrame,
) -> alt.LayerChart:
    """EUR/PLN na lewej osi, złoto NBP (PLN/oz) na prawej. Skale Y niezależne.

    Warstwy muszą być płaskie (siblings). Zagnieżdżony ``alt.layer(eur+rules, gold)``
    z ``resolve_scale(y=independent)`` w Streamlit/Vega-Lite gubi lewą oś EUR.
    Pionowe linie miesięcy: tylko ``x`` (pełna wysokość widoku) — bez ``y``/``y2``.
    """
    layers: list[alt.Chart] = []
    if not month_lines.empty:
        layers.append(
            alt.Chart(month_lines)
            .mark_rule(color="#666666", strokeWidth=1, opacity=0.45)
            .encode(x=alt.X(f"{DATE_COL}:T", title="Data"))
        )
    layers.append(
        alt.Chart(eur)
        .mark_line(color=EUR_COLOR)
        .encode(
            x=alt.X(f"{DATE_COL}:T", title="Data"),
            y=alt.Y(
                f"{RATE_COL}:Q",
                title="EUR/PLN",
                scale=alt.Scale(zero=False),
                axis=alt.Axis(orient="left", titleColor=EUR_COLOR),
            ),
            tooltip=[
                alt.Tooltip(f"{DATE_COL}:T", title="Data"),
                alt.Tooltip(f"{RATE_COL}:Q", title="EUR/PLN", format=".4f"),
            ],
        )
    )
    if gold.empty:
        return alt.layer(*layers).properties(height=CHART_HEIGHT)

    layers.append(
        alt.Chart(gold)
        .mark_line(color=GOLD_COLOR)
        .encode(
            x=alt.X(f"{DATE_COL}:T", title="Data"),
            y=alt.Y(
                f"{GOLD_COL}:Q",
                title=f"Złoto {GOLD_UNIT}",
                scale=alt.Scale(zero=False),
                axis=alt.Axis(orient="right", titleColor=GOLD_COLOR),
            ),
            tooltip=[
                alt.Tooltip(f"{DATE_COL}:T", title="Data"),
                alt.Tooltip(f"{GOLD_COL}:Q", title=f"Złoto {GOLD_UNIT}", format=",.2f"),
            ],
        )
    )
    return (
        alt.layer(*layers)
        .resolve_scale(y="independent")
        .properties(height=CHART_HEIGHT)
    )


def render_fx() -> None:
    st.subheader("FX — EUR/PLN i złoto (NBP)")

    try:
        with st.spinner("Ładowanie kursów NBP..."):
            history = _load_eur_fx_history()
    except Exception as exc:
        st.error("Nie udało się wczytać historii FX.")
        st.exception(exc)
        return

    if history.empty:
        st.warning("Brak danych FX w cache NBP.")
        return

    chart_history = _last_months(history, CHART_MONTHS)
    if chart_history.empty:
        st.warning(f"Brak notowań EUR z ostatnich {CHART_MONTHS} miesięcy.")
        return

    gold_warning = None
    gold_window = pd.DataFrame(columns=[DATE_COL, GOLD_COL])
    try:
        gold_window = _load_gold_window(
            pd.Timestamp(chart_history[DATE_COL].min()).date().isoformat(),
            pd.Timestamp(chart_history[DATE_COL].max()).date().isoformat(),
        )
    except Exception as exc:
        gold_warning = exc

    latest = chart_history.iloc[-1]
    first = chart_history.iloc[0]
    latest_rate = float(latest[RATE_COL])
    first_rate = float(first[RATE_COL])
    delta = latest_rate - first_rate
    delta_pct = (delta / first_rate * 100) if first_rate else 0.0

    gold_latest_price = None
    gold_latest_date = None
    gold_delta = None
    gold_delta_pct = None
    if gold_warning is not None:
        st.warning("Nie udało się wczytać ceny złota NBP. Wykres pokazuje tylko EUR/PLN.")
        st.exception(gold_warning)
    elif not gold_window.empty:
        gold_latest = gold_window.iloc[-1]
        gold_first = gold_window.iloc[0]
        gold_latest_price = float(gold_latest[GOLD_COL])
        gold_latest_date = pd.Timestamp(gold_latest[DATE_COL]).date().isoformat()
        gold_first_price = float(gold_first[GOLD_COL])
        gold_delta = gold_latest_price - gold_first_price
        gold_delta_pct = (gold_delta / gold_first_price * 100) if gold_first_price else 0.0

    st.markdown(
        """
        <style>
        .st-key-fx_metrics [data-testid="stMetricLabel"] { font-size: 0.75rem; }
        .st-key-fx_metrics [data-testid="stMetricValue"] { font-size: 1.75rem; }
        .st-key-fx_metrics [data-testid="stMetricDelta"] { font-size: 0.8rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    with st.container(key="fx_metrics"):
        col_rate, col_date, col_delta, col_count = st.columns(4)
        with col_rate:
            st.metric("Ostatni kurs EUR", f"{latest_rate:.4f} PLN")
            if gold_latest_price is not None:
                st.metric("Ostatnia cena złota", _pln_oz(gold_latest_price))
        with col_date:
            st.metric(
                "Data ostatniego kursu",
                pd.Timestamp(latest[DATE_COL]).date().isoformat(),
            )
            if gold_latest_date is not None:
                st.metric("Data ceny złota", gold_latest_date)
        with col_delta:
            st.metric(
                f"Zmiana EUR ({CHART_MONTHS} mies.)",
                f"{delta:+.4f} PLN",
                f"{delta_pct:+.1f}%",
            )
            if gold_delta is not None and gold_delta_pct is not None:
                st.metric(
                    f"Zmiana złota ({CHART_MONTHS} mies.)",
                    _pln_oz(gold_delta, signed=True),
                    f"{gold_delta_pct:+.1f}%",
                )
        with col_count:
            st.metric(
                "Notowania EUR w oknie",
                f"{len(chart_history):,}".replace(",", " "),
            )

    st.caption(
        f"Wykres: ostatnie {CHART_MONTHS} miesięcy. "
        "Lewa oś: EUR/PLN (NBP tabela A). "
        "Prawa oś: cena złota NBP, PLN za uncję trojańską (31,1034768 g) próby 1000 — nie cena monet bulionowych."
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

    st.altair_chart(
        build_fx_chart(chart_history, gold_window, month_lines),
        width="stretch",
    )

    with st.expander("Tabela kursów (okno wykresu)", expanded=False):
        display = chart_history.copy()
        if not gold_window.empty:
            display = display.merge(gold_window, on=DATE_COL, how="outer")
            display = display.sort_values(DATE_COL)
        display[DATE_COL] = display[DATE_COL].dt.strftime("%Y-%m-%d")
        rename = {DATE_COL: "Data", RATE_COL: "EUR/PLN"}
        if GOLD_COL in display.columns:
            rename[GOLD_COL] = f"Złoto {GOLD_UNIT}"
        display = display.rename(columns=rename)
        st.dataframe(display.iloc[::-1], width="stretch", hide_index=True, height=420)
