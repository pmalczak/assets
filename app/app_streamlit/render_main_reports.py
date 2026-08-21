from __future__ import annotations

import io
from contextlib import redirect_stdout

from datetime import date

import pandas as pd
import streamlit as st

from app_proc.calculate_assets import ASSETS_SNAPSHOT_STEP
from app_proc.recalculate_snapshots import run_snapshot_job_isolated
from app_proc.snapshots import snapshots_directory, load_snapshot, list_snapshot_files
from app_streamlit.build_data import build_portfolio_history_from_snapshots
from app_streamlit.safe_download import dataframe_for_streamlit
from importers.assets.data_model import AssetsDef


@st.cache_data(show_spinner=False)
def load_snapshot_for_date(snapshot_date: date) -> pd.DataFrame:
    path = snapshots_directory() / f"{snapshot_date:%Y-%m-%d}.parquet"
    if not path.is_file():
        return pd.DataFrame()
    return load_snapshot(path)


def _clear_reports_related_cache() -> None:
    build_portfolio_history_from_snapshots.clear()
    load_snapshot_for_date.clear()


def render_main_reports(snapshot_date: date | None, assets: pd.DataFrame):
    from asset_reports import rap1, rap2

    st.subheader("Wartość aktywów")

    today = date.today()
    btn_col, info_col = st.columns([1, 3])
    with btn_col:
        generate = st.button(
            f"Generuj snapshot ({today:%Y-%m-%d})",
            key="generate_today_snapshot_button",
            type="primary",
            help="Przelicza snapshot na dziś bezwarunkowo — także gdy plik już istnieje.",
        )
    with info_col:
        st.caption(
            "Przebudowuje snapshot na dziś w osobnym procesie "
            f"(`{ASSETS_SNAPSHOT_STEP}/{today:%Y-%m-%d}.parquet`). "
            "Źródła (`01 source`) zostają z DATA_STEP, jeśli są aktualne."
        )

    if generate:
        try:
            with st.spinner(f"Generowanie snapshotu {today:%Y-%m-%d}..."):
                results = run_snapshot_job_isolated(weekly=False, force_read_all_data=False)
            if not results:
                raise RuntimeError("Proces snapshotu nie zwrócił wyniku.")
            result = results[0]
            _clear_reports_related_cache()
            st.session_state["reports_last_generated_snapshot"] = result.to_row()
            st.success(
                f"Snapshot {result.valuation_date:%Y-%m-%d}: "
                f"{result.rows} wierszy, suma PLN {result.total_pln:,}".replace(",", " ")
            )
            st.rerun()
        except Exception as exc:
            st.error("Nie udało się wygenerować snapshotu na dziś.")
            st.exception(exc)
            return

    last_generated = st.session_state.get("reports_last_generated_snapshot")
    if last_generated:
        st.caption(
            f"Ostatnio wygenerowano w tej sesji: {last_generated['valuation_date']} "
            f"({last_generated['rows']} wierszy)."
        )

    snapshot_files = list_snapshot_files(snapshots_directory())
    if not snapshot_files:
        st.warning(
            f"Brak snapshotow w katalogu `{snapshots_directory()}`. "
            "Użyj przycisku powyżej albo uruchom "
            "`maintenance/recalculate_weekly_assets_snapshots.py`."
        )
        return

    available_dates = [item[0] for item in snapshot_files]
    default_index = len(available_dates) - 1
    if snapshot_date in available_dates:
        default_index = available_dates.index(snapshot_date)
    if today in available_dates:
        default_index = available_dates.index(today)

    selected_date = st.selectbox(
        "Data snapshotu",
        options=available_dates,
        index=default_index,
        format_func=lambda d: d.isoformat(),
    )
    if selected_date != snapshot_date:
        assets = load_snapshot_for_date(selected_date)

    if assets.empty:
        st.warning(f"Brak danych w snapshotcie {selected_date:%Y-%m-%d}.")
        return

    st.caption(f"Zrodlo: `{ASSETS_SNAPSHOT_STEP}/{selected_date:%Y-%m-%d}.parquet`")

    typ = assets[AssetsDef.TYPE].astype(str)
    cash_pool = assets[typ.str.startswith("cash_pool.")]
    investments = assets[typ.str.startswith("investment.")]

    st.markdown("**Cash pool**")
    st.dataframe(dataframe_for_streamlit(cash_pool), width="stretch", hide_index=True, height=360)

    st.markdown("**Inwestycje**")
    st.dataframe(dataframe_for_streamlit(investments), width="stretch", hide_index=True, height=360)

    st.markdown("**RAP 2**")
    rap2_buffer = io.StringIO()
    with redirect_stdout(rap2_buffer):
        rap2(assets)
    st.code(rap2_buffer.getvalue().strip(), language=None)

    st.markdown("**RAP 1**")
    st.code(rap1(assets).to_string(col_space=15), language=None)
