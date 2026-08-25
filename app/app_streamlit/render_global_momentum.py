# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

_SANDBOX = Path(__file__).resolve().parents[1] / "sandbox"
if str(_SANDBOX) not in sys.path:
    sys.path.insert(0, str(_SANDBOX))

from global_momentum_benchmarks import run_benchmarks
from global_momentum_common import format_metric_table
from global_momentum_u8_ranking import run_u7_ranking

_RANKING_SCHEMA = 4
_RANKING_AS_TODAY_SCHEMA = 2
_BENCHMARK_SCHEMA = 8
_SECTION_RANKING = "Ranking U7"
_SECTION_RANKING_AS_TODAY = "Ranking U7 as_today"
_SECTION_BENCHMARK = "Benchmark"


@st.cache_data(show_spinner=False)
def _load_u7_ranking(_schema: int = _RANKING_SCHEMA) -> dict:
    return run_u7_ranking()


@st.cache_data(show_spinner=False)
def _load_u7_ranking_as_today(_schema: int = _RANKING_AS_TODAY_SCHEMA) -> dict:
    return run_u7_ranking(include_partial_month=True)


@st.cache_data(show_spinner=False)
def _load_benchmarks(_schema: int = _BENCHMARK_SCHEMA) -> dict:
    raw = run_benchmarks()
    return {
        key: value
        for key, value in raw.items()
        if key
        not in {
            "bt8",
            "u7_equal_weight",
            "benchmarks",
            "polish_cpi",
        }
    }


def render_global_momentum() -> None:
    st.subheader("Global momentum")
    st.caption(
        "Ranking operacyjny Universe 7 (koniec minionego miesiąca), "
        "nowcast as_today na ostatnim wspólnym close, "
        "oraz historyczny backtest / benchmarki. "
        "Ranking korzysta z DATA_STEP; backtest używa walidowanych adjusted close z yfinance."
    )

    if st.button("Odśwież dane", key="global_momentum_refresh"):
        _load_u7_ranking.clear()
        _load_u7_ranking_as_today.clear()
        _load_benchmarks.clear()
        st.rerun()

    section = st.pills(
        "Widok",
        options=[_SECTION_RANKING, _SECTION_RANKING_AS_TODAY, _SECTION_BENCHMARK],
        default=_SECTION_RANKING,
        required=True,
        key="global_momentum_view",
        width="stretch",
    )

    if section == _SECTION_RANKING:
        _render_ranking(as_today=False)
    elif section == _SECTION_RANKING_AS_TODAY:
        _render_ranking(as_today=True)
    else:
        _render_benchmarks()


def _render_ranking(*, as_today: bool = False) -> None:
    loader = _load_u7_ranking_as_today if as_today else _load_u7_ranking
    try:
        with st.spinner(
            "Liczenie rankingu U7 as_today..." if as_today else "Liczenie rankingu U7..."
        ):
            result = loader()
    except Exception as exc:
        st.error(
            "Nie udało się policzyć rankingu U7 as_today."
            if as_today
            else "Nie udało się policzyć rankingu U7."
        )
        st.exception(exc)
        return

    if as_today:
        st.caption(
            "Nowcast MTD: ten sam ranking 3/6/12M + SMA10, ostatnia obserwacja = "
            "ostatni wspólny close ETF. To nie jest sygnał rebalance na nowy miesiąc. "
            "Przy nazwie vs Ranking U7: * zostaje w TOP3, + weszło, - wypadło, . poza TOP3."
        )

    if not result["ready"]:
        if result.get("no_common_close"):
            st.warning(
                "Brak wspólnej daty close dla wszystkich ETF-ów Universe 7."
            )
        else:
            st.warning(
                "Brak kompletnej daty sygnału Universe 7 na cenach ETF wykonania. "
                f"Ostatni zakończony miesiąc: {result['latest_full_month']}. "
                f"Minimum obserwacji: {result['min_observations']}."
            )
        availability = result["availability"].copy()
        for column in ("First", "Last", "Ready Through"):
            availability[column] = availability[column].map(
                lambda value: "" if value is None else str(value)
            )
        st.dataframe(availability, width="stretch", hide_index=True)
        return

    if as_today:
        st.markdown(f"**Ostatni close:** {result['signal_date']}")
    else:
        st.markdown(f"**Data sygnału:** {result['signal_date']}")
    ranking = result["ranking"].copy()
    st.dataframe(
        ranking,
        width="stretch",
        hide_index=True,
        column_config={
            "3M": st.column_config.NumberColumn(format="percent"),
            "6M": st.column_config.NumberColumn(format="percent"),
            "12M": st.column_config.NumberColumn(format="percent"),
            "Score": st.column_config.NumberColumn(format="percent"),
            "Price": st.column_config.NumberColumn(format="%.2f"),
            "SMA10": st.column_config.NumberColumn(format="%.2f"),
        },
    )

    st.markdown("**Alokacja TOP3**")
    allocation = result["allocation"].copy()
    st.dataframe(
        allocation,
        width="stretch",
        hide_index=True,
        column_config={"Weight": st.column_config.NumberColumn(format="percent")},
    )


def _render_benchmarks() -> None:
    try:
        with st.spinner("Liczenie backtestu i benchmarków..."):
            result = _load_benchmarks()
    except Exception as exc:
        st.error("Nie udało się policzyć benchmarków Global Momentum.")
        st.exception(exc)
        return

    strategy = result["strategy_comparison"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("CAGR U7", f"{strategy.loc['CAGR', 'GM U7']:.2%}")
    c2.metric(
        "CAGR U7 EW",
        f"{strategy.loc['CAGR', 'U7 Equal Weight']:.2%}",
        f"{strategy.loc['CAGR', 'U7 Equal Weight'] - strategy.loc['CAGR', 'GM U7']:.2%}",
    )
    c3.metric(
        "CAGR All-World",
        f"{strategy.loc['CAGR', 'All-World Buy & Hold']:.2%}",
        f"{strategy.loc['CAGR', 'All-World Buy & Hold'] - strategy.loc['CAGR', 'GM U7']:.2%}",
    )
    c4.metric(
        "Max DD U7",
        f"{strategy.loc['Max Drawdown', 'GM U7']:.2%}",
    )

    period = result["comparison_period"]
    cpi_through = result["cpi_through"]
    caption = "Strategy vs benchmarks"
    if period is not None:
        caption += f" — okres {period[0]} → {period[1]}"
    if cpi_through is not None:
        caption += f"; CPI PL do {cpi_through}"
    st.caption(caption)

    if not strategy.empty:
        st.markdown("**Strategy vs benchmarks**")
        st.dataframe(format_metric_table(strategy), width="stretch")

    annual = result["annual"].copy()
    st.markdown("**Zwroty roczne**")
    st.dataframe(
        annual,
        width="stretch",
        column_config={
            column: st.column_config.NumberColumn(format="percent")
            for column in annual.columns
        },
    )

    equity = result["equity"].copy()
    equity.index = pd.to_datetime(equity.index)
    st.markdown("**Krzywa kapitału (EUR)**")
    st.line_chart(equity, width="stretch")

    drawdowns = result["drawdown"].copy()
    drawdowns.index = pd.to_datetime(drawdowns.index)
    st.markdown("**Drawdown**")
    st.line_chart(drawdowns, width="stretch")


