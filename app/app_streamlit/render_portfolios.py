# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from app_streamlit.render_global_momentum import _load_benchmarks
from app_streamlit.safe_download import dataframe_for_streamlit
from global_momentum.global_momentum_benchmarks import GM_U7_LABEL
from importers.assets.data_model import AssetsDef
from portfolios.assignment import (
    KNOWN_PORTFOLIOS,
    PORTFOLIO_GM,
    ROLE_EXECUTION,
    ROLE_OVERLAY,
    assets_in_portfolio,
    load_portfolio_nav_history,
    nav_pln_for_portfolio,
)
from portfolios.composition import compose_gm_composition, load_gm_broker_holdings
from portfolios.nav_path import nav_path_metrics, rebased_overlap

_PORTFOLIO_NAV_SCHEMA = 1
_COMPOSITION_COLUMNS = (
    AssetsDef.ID,
    AssetsDef.DESCR,
    AssetsDef.TYPE,
    AssetsDef.VALUE_PLN,
)


@st.cache_data(show_spinner=False)
def _load_portfolio_nav(portfolio_name: str, _schema: int = _PORTFOLIO_NAV_SCHEMA) -> pd.Series:
    return load_portfolio_nav_history(portfolio_name)


def render_portfolios() -> None:
    from app_streamlit.build_data import build_data

    data = build_data()
    latest_snapshot = data["latest_snapshot"]
    latest_snapshot_date = data["latest_snapshot_date"]
    if not isinstance(latest_snapshot, pd.DataFrame):
        latest_snapshot = pd.DataFrame()

    st.subheader("Portfele")
    st.caption(
        "NAV i skład nazwanych portfeli ze snapshotów. "
        "NAV zawiera dopłaty — to nie XIRR i nie czysty TWR. "
        f"Porównanie do backtestu U7 tylko dla {PORTFOLIO_GM}."
    )

    if st.button("Odśwież NAV", key="portfolios_refresh"):
        _load_portfolio_nav.clear()
        _load_benchmarks.clear()
        st.rerun()

    selected = st.pills(
        "Portfel",
        options=list(KNOWN_PORTFOLIOS),
        default=PORTFOLIO_GM,
        required=True,
        key="portfolios_selected",
        width="stretch",
    )

    if latest_snapshot.empty or latest_snapshot_date is None:
        st.warning("Brak snapshotu portfela — wygeneruj snapshot w Wartość aktywów.")
        return

    st.markdown(f"**Snapshot:** {latest_snapshot_date.isoformat()}")

    if selected == PORTFOLIO_GM:
        _render_gm_composition(latest_snapshot, latest_snapshot_date)
    else:
        _render_generic_composition(latest_snapshot, selected)

    _render_nav_path(selected)


def _render_generic_composition(snapshot: pd.DataFrame, portfolio_name: str) -> None:
    total_nav = nav_pln_for_portfolio(snapshot, portfolio_name)
    st.metric(f"NAV {portfolio_name}", f"{total_nav:,.0f} PLN".replace(",", " "))
    table = _composition_table(snapshot, portfolio_name)
    if table.empty:
        st.info(f"Brak wierszy w tym snapshocie dla {portfolio_name}.")
        return
    st.dataframe(
        dataframe_for_streamlit(table),
        width="stretch",
        hide_index=True,
        column_config={
            AssetsDef.VALUE_PLN: st.column_config.NumberColumn(format="%.0f"),
        },
    )


def _composition_table(snapshot: pd.DataFrame, portfolio_name: str) -> pd.DataFrame:
    part = assets_in_portfolio(snapshot, portfolio_name)
    if part is None or part.empty:
        return pd.DataFrame()
    cols = [column for column in _COMPOSITION_COLUMNS if column in part.columns]
    if not cols:
        return pd.DataFrame()
    out = part[cols].copy()
    if AssetsDef.VALUE_PLN in out.columns:
        out[AssetsDef.VALUE_PLN] = pd.to_numeric(out[AssetsDef.VALUE_PLN], errors="coerce").fillna(0)
        out = out.sort_values(AssetsDef.VALUE_PLN, ascending=False)
    return out


def _render_gm_composition(
    latest_snapshot: pd.DataFrame,
    latest_snapshot_date: date,
) -> None:
    st.caption(
        f"Wykonanie strategii: DEGIRO + XTB. Złoto jest overlay w NAV portfela {PORTFOLIO_GM}, "
        "nie nogą rankingu U7. Data snapshotu ≠ data sygnału U7. "
        "To nie jest XIRR per ticker."
    )

    holdings: dict = {}
    holdings_warnings: list[str] = []
    try:
        with st.spinner("Rozbicie pozycji / gotówki brokerów..."):
            holdings, holdings_warnings = load_gm_broker_holdings(latest_snapshot_date)
    except Exception as exc:
        holdings_warnings = [f"Nie udało się wczytać holdings: {exc}"]

    for msg in holdings_warnings:
        st.warning(msg)

    table = compose_gm_composition(latest_snapshot, holdings)
    total_nav = float(table["NAV PLN"].sum())
    execution_nav = float(table.loc[table["Rola"] == ROLE_EXECUTION, "NAV PLN"].sum())
    overlay_nav = float(table.loc[table["Rola"] == ROLE_OVERLAY, "NAV PLN"].sum())

    c1, c2, c3 = st.columns(3)
    c1.metric(f"NAV {PORTFOLIO_GM}", f"{total_nav:,.0f} PLN".replace(",", " "))
    c2.metric("Wykonanie (DEGIRO+XTB)", f"{execution_nav:,.0f} PLN".replace(",", " "))
    c3.metric("Overlay (złoto)", f"{overlay_nav:,.0f} PLN".replace(",", " "))

    missing = table.loc[~table["w_snapshocie"], "Składnik"].tolist()
    if missing:
        st.info("Brak w tym snapshocie: " + ", ".join(missing))

    display = table.drop(columns=["id", "w_snapshocie"])
    st.dataframe(
        display,
        width="stretch",
        hide_index=True,
        column_config={
            "NAV PLN": st.column_config.NumberColumn(format="%.0f"),
            "Udział": st.column_config.NumberColumn(format="percent"),
            "Pozycje PLN": st.column_config.NumberColumn(format="%.0f"),
            "Gotówka PLN": st.column_config.NumberColumn(format="%.0f"),
        },
    )


def _render_nav_path(portfolio_name: str) -> None:
    compare_u7 = portfolio_name == PORTFOLIO_GM
    if compare_u7:
        st.markdown("**Ścieżka NAV vs backtest U7**")
        st.caption(
            f"NAV portfela {PORTFOLIO_GM} ze snapshotów (PLN) zawiera dopłaty — to nie XIRR i nie czysty TWR bez CF. "
            "Porównanie: obie serie = 100 na wspólnym starcie. Backtest U7 to stały kapitał (EUR)."
        )
    else:
        st.markdown("**Ścieżka NAV**")
        st.caption(
            "NAV ze snapshotów zawiera dopłaty — to nie XIRR i nie czysty TWR."
        )

    try:
        with st.spinner(f"Ładowanie historii NAV {portfolio_name}..."):
            portfolio_nav = _load_portfolio_nav(portfolio_name)
    except Exception as exc:
        st.error(f"Nie udało się złożyć ścieżki NAV portfela {portfolio_name}.")
        st.exception(exc)
        return

    portfolio_nav = portfolio_nav.rename(f"Portfel {portfolio_name} NAV")
    metrics = nav_path_metrics(portfolio_nav)
    if metrics:
        m1, m2, m3 = st.columns(3)
        m1.metric(
            "CAGR NAV",
            f"{metrics['CAGR']:.2%}" if "CAGR" in metrics else "—",
        )
        m2.metric("Max DD NAV", f"{metrics['Max Drawdown']:.2%}")
        m3.metric("Zmiana NAV", f"{metrics['Total Return']:.2%}")
    elif portfolio_nav.empty:
        st.info(f"Brak historii snapshotów dla portfela {portfolio_name}.")
        return
    else:
        st.info("Za mało dodatnich punktów NAV, żeby policzyć CAGR / DD.")

    if not compare_u7:
        if not portfolio_nav.empty:
            st.line_chart(portfolio_nav, width="stretch")
        return

    try:
        with st.spinner("Ładowanie backtestu U7 do porównania..."):
            benchmarks = _load_benchmarks()
    except Exception as exc:
        st.warning("Backtest U7 niedostępny — pokazuję samą ścieżkę NAV.")
        st.exception(exc)
        if not portfolio_nav.empty:
            st.line_chart(portfolio_nav, width="stretch")
        return

    u7_equity = pd.Series(dtype=float)
    equity = benchmarks.get("equity")
    if isinstance(equity, pd.DataFrame) and GM_U7_LABEL in equity.columns:
        u7_equity = equity[GM_U7_LABEL].copy()
        u7_equity.name = GM_U7_LABEL
    comparison = rebased_overlap(portfolio_nav, u7_equity)
    if comparison.empty:
        st.info(f"Brak wspólnego okresu NAV portfela {PORTFOLIO_GM} i backtestu U7.")
        st.line_chart(portfolio_nav, width="stretch")
        return
    st.line_chart(comparison, width="stretch")
