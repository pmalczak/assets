from __future__ import annotations

import io
from contextlib import redirect_stdout

from datetime import date

import pandas as pd
import streamlit as st

from app_proc.calculate_assets import ASSETS_SNAPSHOT_STEP
from app_proc.snapshots import snapshots_directory, load_snapshot, list_snapshot_files


@st.cache_data(show_spinner=False)
def load_snapshot_for_date(snapshot_date: date) -> pd.DataFrame:
    path = snapshots_directory() / f"{snapshot_date:%Y-%m-%d}.parquet"
    if not path.is_file():
        return pd.DataFrame()
    return load_snapshot(path)


def render_main_reports(snapshot_date: date | None, assets: pd.DataFrame):
    from asset_reports import rap1, rap2

    st.subheader("Raporty (jak w main.py)")

    snapshot_files = list_snapshot_files(snapshots_directory())
    if not snapshot_files:
        st.warning(
            f"Brak snapshotow w katalogu `{snapshots_directory()}`. "
            "Uruchom `maintenance/recalculate_weekly_assets_snapshots.py`."
        )
        return

    available_dates = [item[0] for item in snapshot_files]
    default_index = len(available_dates) - 1
    if snapshot_date in available_dates:
        default_index = available_dates.index(snapshot_date)

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

    st.markdown("**Pelna lista aktywow**")
    st.dataframe(assets, width='stretch', hide_index=True, height=360)

    st.markdown("**RAP 2**")
    rap2_buffer = io.StringIO()
    with redirect_stdout(rap2_buffer):
        rap2(assets)
    st.code(rap2_buffer.getvalue().strip(), language=None)

    st.markdown("**RAP 1**")
    st.code(rap1(assets).to_string(col_space=15), language=None)
