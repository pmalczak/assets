# -*- coding: utf-8 -*-
"""Top-level Portfel: snapshot + RAP 1 obok, poniżej zawsze belka nazwanych portfeli."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from app_proc.assets_snapshot_step import assets_snapshot_resource
from app_proc.recalculate_snapshots import run_snapshot_job_isolated
from app_proc.snapshots import list_snapshot_files, snapshots_directory
from app_streamlit.build_data import build_data
from app_streamlit.render_main_reports import load_snapshot_for_date, render_main_reports
from app_streamlit.render_portfolios import render_portfolios
from portfolio_cf.products import invalidate_portfolio_cf


def _clear_reports_related_cache() -> None:
    build_data.clear()
    load_snapshot_for_date.clear()
    try:
        from app_streamlit.render_portfolios import _load_gm_positions, _load_portfolio_nav

        _load_portfolio_nav.clear()
        _load_gm_positions.clear()
    except Exception:
        pass


def _run_generate_snapshot(today: date) -> None:
    try:
        with st.spinner(f"Generowanie snapshotu {today:%Y-%m-%d}..."):
            results = run_snapshot_job_isolated(weekly=False, force_read_all_data=False)
        if not results:
            raise RuntimeError("Proces snapshotu nie zwrócił wyniku.")
        result = results[0]
        _clear_reports_related_cache()
        invalidate_portfolio_cf(result.valuation_date)
        st.session_state["reports_last_generated_snapshot"] = result.to_row()
        st.success(
            f"Snapshot {result.valuation_date:%Y-%m-%d}: "
            f"{result.rows} wierszy, suma PLN {result.total_pln:,}".replace(",", " ")
        )
        st.rerun()
    except Exception as exc:
        st.error("Nie udało się wygenerować snapshotu na dziś.")
        st.exception(exc)


def render_portfolio_shell(
    snapshot_date: date | None,
    assets: pd.DataFrame,
) -> None:
    """Kontrolki snapshota + RAP 1 obok; poniżej zawsze widok nazwanych portfeli."""
    st.subheader("Portfel")

    today = date.today()
    snapshot_files = list_snapshot_files(snapshots_directory())

    controls_col, rap1_col = st.columns([1, 1], vertical_alignment="top", gap="medium")

    with controls_col:
        generate = st.button(
            f"Generuj snapshot ({today:%Y-%m-%d})",
            key="generate_today_snapshot_button",
            type="primary",
            help="Przelicza snapshot na dziś bezwarunkowo — także gdy plik już istnieje.",
            width="stretch",
        )
        st.caption(
            "Przebudowuje snapshot na dziś w osobnym procesie "
            f"(`{assets_snapshot_resource(today)}`). "
            "Źródła (`01 source`) zostają z DATA_STEP, jeśli są aktualne."
        )

    if generate:
        _run_generate_snapshot(today)
        return

    with controls_col:
        last_generated = st.session_state.get("reports_last_generated_snapshot")
        if last_generated:
            st.caption(
                f"Ostatnio wygenerowano w tej sesji: {last_generated['valuation_date']} "
                f"({last_generated['rows']} wierszy)."
            )

    if not snapshot_files:
        with controls_col:
            st.warning(
                f"Brak snapshotow w katalogu `{snapshots_directory()}`. "
                "Użyj przycisku powyżej albo "
                "`uv run python -m app_proc.snapshot_cli --weekly`."
            )
        return

    available_dates = [item[0] for item in snapshot_files]
    default_index = len(available_dates) - 1
    if snapshot_date in available_dates:
        default_index = available_dates.index(snapshot_date)
    if today in available_dates:
        default_index = available_dates.index(today)

    with controls_col:
        selected_date = st.selectbox(
            "Data snapshotu",
            options=available_dates,
            index=default_index,
            format_func=lambda d: d.isoformat(),
        )

    if selected_date != snapshot_date:
        assets = load_snapshot_for_date(selected_date)

    if assets.empty:
        with controls_col:
            st.warning(f"Brak danych w snapshotcie {selected_date:%Y-%m-%d}.")
        return

    with controls_col:
        st.caption(
            f"Źródło: `{assets_snapshot_resource(selected_date)}`. "
            "RAP 1: **XIRR** = lokalny (FX_T), **XIRR PLN** = spot (FX_t); "
            "filtr pozycji z sidebara. Semantyka: `Cursor_rules.md` → XIRR portfela a FX."
        )

    with rap1_col:
        render_main_reports(selected_date, assets)

    render_portfolios(selected_date, assets)
