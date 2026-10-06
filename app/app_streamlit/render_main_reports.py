from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from app_proc.snapshots import load_snapshot, snapshot_path
from app_proc.ui_prefs import current_sold_filter
from portfolio_cf.products import load_portfolio_metrics_map
from portfolios.composition import split_broker_nav_for_instrument_overrides


@st.cache_data(show_spinner=False)
def load_snapshot_for_date(snapshot_date: date) -> pd.DataFrame:
    path = snapshot_path(snapshot_date)
    if not path.is_file():
        return pd.DataFrame()
    return load_snapshot(path)


def render_main_reports(snapshot_date: date, assets: pd.DataFrame) -> None:
    """RAP 1 dla przekazanego snapshota (prawa kolumna w shell Portfel)."""
    from asset_reports import format_rap_table, rap1

    if assets.empty:
        st.warning(f"Brak danych w snapshotcie {snapshot_date:%Y-%m-%d}.")
        return

    assets = split_broker_nav_for_instrument_overrides(assets, snapshot_date)

    sold_filter = current_sold_filter()
    try:
        with st.spinner("XIRR portfeli do RAP 1..."):
            metrics = load_portfolio_metrics_map(snapshot_date, sold_filter)
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
