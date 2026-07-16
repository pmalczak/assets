# -*- coding: utf-8 -*-
"""
Dashboard wartosci portfela oparty o snapshoty DATA_STEP (09 assets).

Uruchomienie:
  cd app
  uv run streamlit run app_assets.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from app_streamlit.build_data import build_portfolio_history_from_snapshots, build_data
from app_streamlit.render_diagnostics import render_diagnostics
from app_streamlit.render_main_reports import load_snapshot_for_date, render_main_reports
from app_streamlit.render_portfolio_history import render_portfolio_history
from app_streamlit.render_roi import render_roi
from app_streamlit.render_snapshot_result import render_snapshot_results
from app_streamlit.render_transaction_search import _load_transactions_cached, render_transaction_search
from app_proc.ui_prefs import TAB_LABELS, TABS_STATE_KEY, load_last_tab, on_tab_changed

from maintenance.move_downloaded_results import (
    ACTION_DELETED_EMPTY,
    ACTION_MOVED,
    ACTION_SKIPPED,
    results_to_dataframe,
)
from move_dowloaded import run_move_downloaded
from app_proc.recalculate_snapshots import (
    SnapshotResult,
    recalculate_today_snapshot,
    recalculate_weekly_snapshots,
)

st.set_page_config(page_title="Assets Dashboard (snapshots)", layout="wide")


def _clear_dashboard_cache() -> None:
    build_portfolio_history_from_snapshots.clear()
    load_snapshot_for_date.clear()
    _load_transactions_cached.clear()


def _run_snapshot_recalculation(*, full_recalculation: bool) -> list[SnapshotResult]:
    if full_recalculation:
        return recalculate_weekly_snapshots(force_read_all_data=True)
    return [recalculate_today_snapshot(force_read_all_data=True)]


def render_import_wyciagow() -> None:
    st.subheader("Import wyciągów")

    home = Path.home()
    st.caption(
        "Przenosi pobrane wyciągi do katalogów w Dropbox:\n"
        f"- mBank: `{home / 'Downloads'}` oraz pliki w `{home / 'Dropbox' / 'INWESTYCJE' / 'assets'}`\n"
        f"- Revolut pm: `{home / 'Dropbox' / 'INWESTYCJE' / 'download' / 'pm'}`\n"
        f"- Revolut gm: `{home / 'Dropbox' / 'INWESTYCJE' / 'download' / 'gm'}`"
    )

    if st.button("Przenieś pliki do ich katalogów", key="move_downloaded_button"):
        try:
            with st.spinner("Przenoszenie plików..."):
                results = run_move_downloaded()
            st.session_state["move_downloaded_results"] = results

            moved = sum(1 for result in results if result.action == ACTION_MOVED)
            if moved > 0:
                with st.spinner("Przeliczanie snapshotu na dziś..."):
                    snapshot_results = _run_snapshot_recalculation(full_recalculation=False)
                st.session_state["snapshot_recalculation_results"] = snapshot_results
                _clear_dashboard_cache()
        except Exception as exc:
            st.error("Nie udało się przenieść plików.")
            st.exception(exc)
            return

    move_results = st.session_state.get("move_downloaded_results")
    if move_results is not None:
        if not move_results:
            st.info("Brak plików do przeniesienia.")
        else:
            moved = sum(1 for result in move_results if result.action == ACTION_MOVED)
            deleted = sum(1 for result in move_results if result.action == ACTION_DELETED_EMPTY)
            skipped = sum(1 for result in move_results if result.action == ACTION_SKIPPED)

            st.markdown("**Przeniesione pliki**")
            c1, c2, c3 = st.columns(3)
            c1.metric("Przeniesione", moved)
            c2.metric("Usunięte (puste)", deleted)
            c3.metric("Pominięte", skipped)
            st.dataframe(
                results_to_dataframe(move_results),
                width="stretch",
                hide_index=True,
                height=360,
            )
    else:
        st.info("Kliknij przycisk, aby przenieść pliki i zobaczyć wyniki.")

    st.divider()
    st.markdown("**Snapshoty portfela (`09 assets`)**")
    st.caption(
        "Po przeniesieniu plików snapshot na dziś jest przeliczany automatycznie. "
        "Możesz też przeliczyć ręcznie."
    )

    full_recalculation = st.checkbox(
        "Pełne przeliczenie (365 dni, wt/sr/pt/nd)",
        value=False,
        key="snapshot_full_recalculation",
    )

    if st.button("Przelicz snapshoty", key="recalculate_snapshots_button"):
        try:
            with st.spinner("Przeliczanie snapshotów..."):
                snapshot_results = _run_snapshot_recalculation(full_recalculation=full_recalculation)
            st.session_state["snapshot_recalculation_results"] = snapshot_results
            _clear_dashboard_cache()
        except Exception as exc:
            st.error("Nie udało się przeliczyć snapshotów.")
            st.exception(exc)
            return

    snapshot_results = st.session_state.get("snapshot_recalculation_results")
    if snapshot_results is not None:
        render_snapshot_results(snapshot_results)


def main():
    st.title("Assets Dashboard (snapshoty DATA_STEP)")

    with st.spinner("Ladowanie snapshotow..."):
        try:
            data = build_data()
        except Exception as e:
            st.error("Wystapil blad podczas wczytywania snapshotow.")
            st.exception(e)
            return

    left, right = st.columns([1, 1])
    with left:
        label = "Ostatni snapshot"
        if data["latest_snapshot_date"]:
            label += f" ({data['latest_snapshot_date']:%Y-%m-%d})"
        st.metric(label, f"{data['snapshot_total_pln']:,.0f} PLN".replace(",", " "))
    with right:
        file_name = "assets_evaluation.xlsx"
        if data["latest_snapshot_date"]:
            file_name = f"assets_evaluation_{data['latest_snapshot_date']:%Y-%m-%d}.xlsx"
        st.download_button(
            label="Pobierz ostatni snapshot (xlsx)",
            data=data["excel_bytes"],
            file_name=file_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            disabled=data["latest_snapshot"].empty,
        )

    if TABS_STATE_KEY not in st.session_state:
        st.session_state[TABS_STATE_KEY] = load_last_tab()

    tab_chart, tab_reports, tab_search, tab_roi, tab_import = st.tabs(
        TAB_LABELS,
        key=TABS_STATE_KEY,
        default=st.session_state[TABS_STATE_KEY],
        on_change=on_tab_changed,
    )

    with tab_chart:
        render_portfolio_history(
            data["history"],
            data["timeline_events"],
            data["latest_snapshot_date"],
        )
        render_diagnostics(data)

    with tab_reports:
        render_main_reports(data["latest_snapshot_date"], data["latest_snapshot"])

    with tab_search:
        render_transaction_search()

    with tab_roi:
        render_roi(data["latest_snapshot_date"])

    with tab_import:
        render_import_wyciagow()


if __name__ == "__main__":
    pd.options.future.infer_string = True
    main()
