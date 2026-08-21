# -*- coding: utf-8 -*-
"""
Dashboard wartosci portfela oparty o snapshoty DATA_STEP (ASSETS_SNAPSHOT_STEP).

Uruchomienie:
  cd app
  uv run streamlit run app_assets.py
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import streamlit as st

from app_proc.ui_prefs import (
    TAB_ASSETS,
    TAB_LABELS,
    TABS_STATE_KEY,
    load_last_tab,
    on_tab_changed,
    render_sold_filter_control,
)
from app_proc.calculate_assets import ASSETS_SNAPSHOT_STEP
from app_proc.data_root import get_cash_pool_root, get_online_data_root
from app_proc.data_steps_root import get_data_steps_root
from app_streamlit.build_data import build_portfolio_history_from_snapshots, build_data
from app_streamlit.render_diagnostics import render_diagnostics
from app_streamlit.render_fx import render_fx
from app_streamlit.render_global_momentum import render_global_momentum
from app_streamlit.render_main_reports import load_snapshot_for_date, render_main_reports
from app_streamlit.render_portfolio_history import render_portfolio_history
from app_streamlit.render_roi import (
    render_roi,
    render_roi_obligacje,
    render_roi_revolut_deposits,
    render_roi_revolut_robo,
)
from app_streamlit.render_snapshot_result import render_snapshot_results
from app_streamlit.render_transaction_search import _load_transactions_cached, render_transaction_search
from app_streamlit.render_validate import render_validate
from app_streamlit.safe_download import opt_in_download_button
from data_step.data_step import DATA_STEP

from maintenance.move_downloaded_results import (
    ACTION_DELETED_EMPTY,
    ACTION_MOVED,
    ACTION_SKIPPED,
    results_to_dataframe,
)
from move_dowloaded import run_move_downloaded
from app_proc.recalculate_snapshots import (
    PORTFOLIO_WINDOW_DAYS,
    SnapshotResult,
    run_snapshot_job_isolated,
)

st.set_page_config(page_title="Assets Dashboard (snapshots)", layout="wide")


def _clear_dashboard_cache() -> None:
    build_portfolio_history_from_snapshots.clear()
    load_snapshot_for_date.clear()
    _load_transactions_cached.clear()


def _run_snapshot_recalculation(*, full_recalculation: bool) -> list[SnapshotResult]:
    return run_snapshot_job_isolated(
        weekly=full_recalculation,
        force_read_all_data=True,
    )


def render_import_wyciagow() -> None:
    st.subheader("Import wyciągów")

    home = Path.home()
    st.caption(
        "Przenosi pobrane wyciągi do katalogów w Dropbox:\n"
        f"- mBank: `{home / 'Downloads'}` oraz luźne CSV w `{get_online_data_root()}` "
        f"→ `{get_cash_pool_root()}`\n"
        f"- Revolut pm: `{home / 'Dropbox' / 'INWESTYCJE' / 'download' / 'pm'}` → `{get_cash_pool_root()}`\n"
        f"- Revolut gm: `{home / 'Dropbox' / 'INWESTYCJE' / 'download' / 'gm'}` → `{get_cash_pool_root()}`\n"
        f"- Trade Republic: `{home / 'Dropbox' / 'INWESTYCJE' / 'download' / 'pm'}` "
        f"(`Eksport transakcji.csv` → `eksport-transakcji_{{od}}_{{do}}.csv`) "
        f"→ `{get_online_data_root() / 'p_traderepublic'}`\n"
        f"- obligacje skarbowe: `{home / 'Downloads'}` "
        f"(`StanRachunkuRejestrowego*.xls`, `HistoriaDyspozycji.xls` "
        f"z nazwą wg zakresu dat dyspozycji) "
        f"→ `{get_online_data_root() / 'obligacjeskarbowe'}`\n"
        f"- DEGIRO: `{home / 'Downloads'}` "
        f"(`Portfolio.csv`, `Transactions.csv`, `Account.csv` "
        f"→ `{{portfolio,transactions,account}}_{{od}}_{{do}}.csv`) "
        f"→ `{get_online_data_root() / 'p_degiro'}`\n"
        f"- XTB: `{home / 'Downloads'}` "
        f"(`55260027_{{od}}_{{do}}*.zip` → rozpakowany `xtb_{{open,closed,cash}}_55260027_{{od}}_{{do}}.xlsx`; "
        f"identyczne `(1)`, `(2)` są pomijane) "
        f"→ `{get_online_data_root() / 'p_xtb'}`"
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
    st.markdown(f"**Snapshoty portfela (`{ASSETS_SNAPSHOT_STEP}`)**")
    st.caption(
        "Po przeniesieniu plików snapshot na dziś jest przeliczany automatycznie. "
        "Możesz też przeliczyć ręcznie."
    )

    full_recalculation = st.checkbox(
        f"Pełne przeliczenie ({PORTFOLIO_WINDOW_DAYS} dni ≈ 6 mies., wt/sr/pt/nd)",
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
    snapshot_path = get_data_steps_root()
    DATA_STEP.init_steps(root=snapshot_path)

    st.title("Assets Dashboard (snapshoty DATA_STEP)")
    render_sold_filter_control()

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
        latest_snapshot = data["latest_snapshot"]

        def _snapshot_xlsx_bytes() -> bytes:
            buf = io.BytesIO()
            latest_snapshot.to_excel(buf, index=False)
            return buf.getvalue()

        opt_in_download_button(
            prepare_label="Przygotuj pobieranie snapshotu (xlsx)",
            prepare_key="prepare_snapshot_xlsx",
            button_label="Pobierz ostatni snapshot (xlsx)",
            data_factory=_snapshot_xlsx_bytes,
            file_name=file_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            download_key="snapshot_xlsx_download",
            disabled=not isinstance(latest_snapshot, pd.DataFrame) or latest_snapshot.empty,
        )

    if TABS_STATE_KEY not in st.session_state:
        st.session_state[TABS_STATE_KEY] = load_last_tab()

    tab_objs = st.tabs(
        TAB_LABELS,
        key=TABS_STATE_KEY,
        default=st.session_state[TABS_STATE_KEY],
        on_change=on_tab_changed,
    )
    active_tab = st.session_state.get(TABS_STATE_KEY, TAB_LABELS[0])
    latest = data["latest_snapshot_date"]

    # Tylko aktywna zakładka — równoległy render wszystkich (Altair + wiele downloadów)
    # na Python 3.14/pyarrow potrafi ubić proces bez tracebacku.
    for tab, label in zip(tab_objs, TAB_LABELS):
        with tab:
            if label != active_tab:
                continue
            if label == TAB_ASSETS:
                render_main_reports(latest, data["latest_snapshot"])
            elif label == "Wykres portfela":
                render_portfolio_history(
                    data["history"],
                    data["timeline_events"],
                    latest,
                )
                render_diagnostics(data)
            elif label == "ROI":
                render_roi(latest)
            elif label == "ROI Revolut robo":
                render_roi_revolut_robo(latest)
            elif label == "ROI Revolut depozyty":
                render_roi_revolut_deposits(latest)
            elif label == "ROI obligacje":
                render_roi_obligacje(latest)
            elif label == "ROI DEGIRO":
                from app_streamlit.render_roi import render_roi_degiro
                render_roi_degiro(latest)
            elif label == "ROI XTB":
                from app_streamlit.render_roi import render_roi_xtb
                render_roi_xtb(latest)
            elif label == "FX":
                render_fx()
            elif label == "Global momentum":
                render_global_momentum()
            elif label == "Import wyciągów":
                render_import_wyciagow()
            elif label == "Wyszukiwanie transakcji":
                render_transaction_search()
            elif label == "Waliduj":
                render_validate()

if __name__ == "__main__":
    # infer_string + pyarrow na CPython 3.14 bywa przyczyną segfaultu Streamlit.
    import faulthandler

    faulthandler.enable(all_threads=True)
    pd.options.future.infer_string = False
    main()
