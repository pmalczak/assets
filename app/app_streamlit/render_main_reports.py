from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from app_proc.calculate_assets import ASSETS_SNAPSHOT_STEP
from app_proc.recalculate_snapshots import run_snapshot_job_isolated
from app_proc.snapshots import snapshots_directory, load_snapshot, list_snapshot_files
from app_proc.ui_prefs import current_sold_filter
from app_streamlit.build_data import build_portfolio_history_from_snapshots
from portfolio_cf.products import invalidate_portfolio_cf, load_portfolio_metrics_map


@st.cache_data(show_spinner=False)
def load_snapshot_for_date(snapshot_date: date) -> pd.DataFrame:
    path = snapshots_directory() / f"{snapshot_date:%Y-%m-%d}.parquet"
    if not path.is_file():
        return pd.DataFrame()
    return load_snapshot(path)


def _clear_reports_related_cache() -> None:
    build_portfolio_history_from_snapshots.clear()
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
        # Po zapisie parquet — wymuś przebudowę ledger/XIRR na tę datę.
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


def render_main_reports(snapshot_date: date | None, assets: pd.DataFrame):
    from asset_reports import format_rap_table, rap1, rap2

    st.subheader("Wartość aktywów")

    today = date.today()
    snapshot_files = list_snapshot_files(snapshots_directory())

    # Góra: kontrolki + RAP1 obok siebie; dół: RAP2 na pełnej szerokości od lewej.
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
            f"(`{ASSETS_SNAPSHOT_STEP}/{today:%Y-%m-%d}.parquet`). "
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
            f"Źródło: `{ASSETS_SNAPSHOT_STEP}/{selected_date:%Y-%m-%d}.parquet`. "
            "Skład portfeli — zakładka Portfele. "
            "XIRR w RAP 1 = lokalny (constant FX_T) z DATA_STEP `11 portfolio_cf` "
            "(filtr pozycji z sidebara); obok XIRR PLN (spot, FX_t)."
        )

    sold_filter = current_sold_filter()
    try:
        with st.spinner("XIRR portfeli do RAP 1..."):
            metrics = load_portfolio_metrics_map(selected_date, sold_filter)
            xirr_by_portfolio = {
                name: row.get("xirr") for name, row in metrics.items()
            }
            xirr_pln_by_portfolio = {
                name: row.get("xirr_pln") for name, row in metrics.items()
            }
    except Exception as exc:
        st.warning(f"Nie udało się policzyć XIRR do RAP 1: {exc}")
        xirr_by_portfolio = {}
        xirr_pln_by_portfolio = {}

    with rap1_col:
        st.code(
            format_rap_table(
                rap1(
                    assets,
                    xirr_by_portfolio=xirr_by_portfolio,
                    xirr_pln_by_portfolio=xirr_pln_by_portfolio,
                )
            ),
            language=None,
        )

    st.markdown("**RAP 2**")
    st.code(format_rap_table(rap2(assets)), language=None)
