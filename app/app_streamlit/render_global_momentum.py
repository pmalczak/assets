# -*- coding: utf-8 -*-
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from importers.assets.instruments import (
    InstrumentMapError,
    apply_gm_instrument_names,
    load_instrument_map,
)
from global_momentum.global_momentum_benchmarks import (
    GM_U7_LABEL,
    U7_EQUAL_WEIGHT_LABEL,
    prepare_strategy_comparison,
    run_benchmarks,
)
from global_momentum.global_momentum_common import format_metric_table
from global_momentum.global_momentum_u8_ranking import (
    RANKING_TICKERS,
    SCORING_CHART_BASE_MONTHS,
    build_scoring_normalized_paths,
    run_u7_ranking,
    scoring_anchor_label,
    scoring_lookback_offsets,
)

_RANKING_SCHEMA = 7
_RANKING_AS_TODAY_SCHEMA = 6
_BENCHMARK_SCHEMA = 9
_ALL_WORLD_LABEL = "All-World Buy & Hold"
_SECTION_RANKING = "Ranking U7"
_SECTION_RANKING_AS_TODAY = "as_today"
_SECTION_BENCHMARK = "Benchmark"
_SCORING_CHART_HEIGHT = 360
_TICKER_TO_ASSET = {ticker: asset for asset, ticker in RANKING_TICKERS.items()}
_SCORING_BASE_OPTIONS = [
    scoring_anchor_label(months) for months in scoring_lookback_offsets()
]
_SCORING_BASE_MONTHS = {
    scoring_anchor_label(months): months for months in scoring_lookback_offsets()
}
_SCORING_BASE_DEFAULT = scoring_anchor_label(SCORING_CHART_BASE_MONTHS)


@st.cache_data(show_spinner=False)
def _load_u7_ranking(_schema: int = _RANKING_SCHEMA) -> dict:
    return run_u7_ranking()


@st.cache_data(show_spinner=False)
def _load_u7_ranking_as_today(_schema: int = _RANKING_AS_TODAY_SCHEMA) -> dict:
    return run_u7_ranking(include_partial_month=True)


@st.cache_data(show_spinner=False)
def _load_benchmarks(schema: int = _BENCHMARK_SCHEMA) -> dict:
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
        "nowcast as_today na ostatnim wspólnym close "
        "oraz historyczny backtest / benchmarki. "
        "Ranking korzysta z DATA_STEP; backtest używa walidowanych adjusted close z yfinance."
    )

    if st.button("Odśwież dane", key="global_momentum_refresh"):
        _load_u7_ranking.clear()
        _load_u7_ranking_as_today.clear()
        _load_benchmarks.clear()
        st.rerun()

    if "global_momentum_view" in st.session_state:
        del st.session_state["global_momentum_view"]
    if st.session_state.get("global_momentum_section") == "Mój GM":
        del st.session_state["global_momentum_section"]

    section = st.pills(
        "Widok",
        options=[
            _SECTION_RANKING,
            _SECTION_RANKING_AS_TODAY,
            _SECTION_BENCHMARK,
        ],
        default=_SECTION_RANKING_AS_TODAY,
        required=True,
        key="global_momentum_section",
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
        result = apply_gm_instrument_names(result, load_instrument_map())
    except InstrumentMapError as exc:
        st.error(str(exc))
        return
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
            "Przy nazwie vs Ranking U7: * zostaje w TOP3, + weszło, - wypadło."
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
        st.markdown(
            f"**Data ostatniej wspólnej sesji wszystkich ETF:** {result['signal_date']}"
        )
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

    _render_scoring_price_chart(result, as_today=as_today)


def _render_scoring_price_chart(result: dict, *, as_today: bool) -> None:
    monthly = result.get("monthly_prices")
    daily = result.get("daily_prices")
    ranking = result.get("ranking")
    signal_date = result.get("signal_date")
    if (
        not isinstance(monthly, pd.DataFrame)
        or monthly.empty
        or not isinstance(ranking, pd.DataFrame)
        or ranking.empty
        or signal_date is None
    ):
        return

    options: list[str] = []
    label_to_asset: dict[str, str] = {}
    for row in ranking.to_dict("records"):
        label = str(row["Asset"])
        asset = _TICKER_TO_ASSET.get(str(row.get("Ticker") or ""))
        if asset is None:
            continue
        options.append(label)
        label_to_asset[label] = asset

    if not options:
        return

    default = [
        str(row["Asset"])
        for row in ranking.to_dict("records")
        if bool(row.get("TOP3")) and str(row["Asset"]) in label_to_asset
    ]
    if not default:
        default = options[: min(3, len(options))]

    selected = st.multiselect(
        "Walory na wykresie SCORING",
        options=options,
        default=default,
        key=(
            "gm_scoring_chart_assets_as_today"
            if as_today
            else "gm_scoring_chart_assets"
        ),
    )
    base_label = st.radio(
        "Punkt referencyjny = 100%",
        options=_SCORING_BASE_OPTIONS,
        index=_SCORING_BASE_OPTIONS.index(_SCORING_BASE_DEFAULT),
        horizontal=True,
        key=(
            "gm_scoring_chart_base_as_today"
            if as_today
            else "gm_scoring_chart_base"
        ),
    )
    if not selected:
        st.caption("Wybierz co najmniej jeden walor, żeby zobaczyć ścieżkę t-12 → t.")
        return

    assets = [label_to_asset[label] for label in selected]
    labels = {label_to_asset[label]: label for label in selected}
    base_months = _SCORING_BASE_MONTHS[base_label]
    daily_frame = daily if isinstance(daily, pd.DataFrame) and not daily.empty else None
    try:
        paths, points = build_scoring_normalized_paths(
            monthly,
            signal_date=signal_date,
            assets=assets,
            labels=labels,
            daily=daily_frame,
            base_months=base_months,
        )
    except KeyError as exc:
        st.warning(f"Nie udało się zbudować wykresu SCORING: {exc}")
        return

    if paths.empty:
        st.warning("Za mało historii miesięcznej do okna t-12 → t.")
        return

    st.markdown(f"**Zmiana cen w oknie SCORING ({base_label} = 100%)**")
    st.caption(
        "Ścieżka: month-end + połowy miesięcy (ostatni daily close ≤ t-0.5, t-1.5, …). "
        f"Markery = t-12 / t-6 / t-3 / t z Score. Wspólna skala: close w {base_label} = 100%."
    )
    st.altair_chart(
        _build_scoring_price_chart(paths, points, base_label=base_label),
        width="stretch",
    )


def _scoring_month_start_grid(paths: pd.DataFrame) -> pd.DataFrame:
    """Vertical grid dates: 1st of each month inside the chart window."""
    empty = pd.DataFrame(columns=["Date"])
    if paths.empty or "Date" not in paths.columns:
        return empty
    dates = pd.to_datetime(paths["Date"], errors="coerce").dropna()
    if dates.empty:
        return empty
    start = dates.min().normalize()
    end = dates.max().normalize()
    month_starts = pd.date_range(start=start, end=end, freq="MS")
    return pd.DataFrame({"Date": month_starts})


def _build_scoring_price_chart(
    paths: pd.DataFrame,
    points: pd.DataFrame,
    *,
    base_label: str = _SCORING_BASE_DEFAULT,
) -> alt.Chart:
    baseline = (
        alt.Chart(pd.DataFrame({"Level": [100.0]}))
        .mark_rule(strokeWidth=3, color="#111111")
        .encode(y="Level:Q")
    )
    month_grid = _scoring_month_start_grid(paths)
    grid = (
        alt.Chart(month_grid)
        .mark_rule(strokeWidth=1, color="#B0B0B0", strokeDash=[4, 3])
        .encode(x="Date:T")
        if not month_grid.empty
        else None
    )
    line = (
        alt.Chart(paths)
        .mark_line()
        .encode(
            x=alt.X("Date:T", title=None),
            y=alt.Y(
                "Level:Q",
                title=f"Indeks ({base_label} = 100%)",
                scale=alt.Scale(zero=False),
            ),
            color=alt.Color("Series:N", title="Walor"),
            tooltip=[
                alt.Tooltip("Date:T", title="Data"),
                alt.Tooltip("Series:N", title="Walor"),
                alt.Tooltip("Level:Q", title="Indeks", format=".1f"),
            ],
        )
    )
    layers: list[alt.Chart] = []
    if grid is not None:
        layers.append(grid)
    layers.extend([baseline, line])
    if not points.empty:
        layers.append(
            alt.Chart(points)
            .mark_point(size=70, filled=True)
            .encode(
                x="Date:T",
                y="Level:Q",
                color=alt.Color("Series:N", title="Walor"),
                shape=alt.Shape("Point:N", title="Punkt SCORING"),
                tooltip=[
                    alt.Tooltip("Date:T", title="Data"),
                    alt.Tooltip("Series:N", title="Walor"),
                    alt.Tooltip("Point:N", title="Punkt"),
                    alt.Tooltip("Level:Q", title="Indeks", format=".1f"),
                ],
            )
        )
    chart = alt.layer(*layers).properties(height=_SCORING_CHART_HEIGHT)
    if not points.empty:
        chart = chart.resolve_scale(shape="independent")
    return chart


def _render_benchmarks() -> None:
    try:
        with st.spinner("Liczenie backtestu i benchmarków..."):
            result = _load_benchmarks()
    except Exception as exc:
        st.error("Nie udało się policzyć benchmarków Global Momentum.")
        st.exception(exc)
        return

    strategy = prepare_strategy_comparison(result.get("strategy_comparison"))
    u7 = result.get("universe7_label", GM_U7_LABEL)
    if strategy.empty or u7 not in strategy.columns:
        st.error("Brak kompletnego porównania strategii (kolumna GM U7).")
        raw = result.get("strategy_comparison")
        if isinstance(raw, pd.DataFrame) and not raw.empty:
            st.dataframe(raw, width="stretch")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("CAGR U7", f"{strategy.loc['CAGR', u7]:.2%}")
    c2.metric(
        "CAGR U7 EW",
        f"{strategy.loc['CAGR', U7_EQUAL_WEIGHT_LABEL]:.2%}",
        f"{strategy.loc['CAGR', U7_EQUAL_WEIGHT_LABEL] - strategy.loc['CAGR', u7]:.2%}",
    )
    c3.metric(
        "CAGR All-World",
        f"{strategy.loc['CAGR', _ALL_WORLD_LABEL]:.2%}",
        f"{strategy.loc['CAGR', _ALL_WORLD_LABEL] - strategy.loc['CAGR', u7]:.2%}",
    )
    c4.metric(
        "Max DD U7",
        f"{strategy.loc['Max Drawdown', u7]:.2%}",
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
