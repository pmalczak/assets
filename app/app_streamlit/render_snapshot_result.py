from __future__ import annotations

import streamlit as st

from app_proc.recalculate_snapshots import SnapshotResult, snapshot_results_to_dataframe


def render_snapshot_results(snapshot_results: list[SnapshotResult]) -> None:
    st.markdown("**Przeliczone snapshoty**")
    if not snapshot_results:
        st.info("Brak przeliczonych snapshotów.")
        return

    total_pln = snapshot_results[-1].total_pln
    c1, c2, c3 = st.columns(3)
    c1.metric("Snapshotów", len(snapshot_results))
    c2.metric("Ostatnia data", snapshot_results[-1].valuation_date.isoformat())
    c3.metric("Suma PLN (ostatni)", f"{total_pln:,}".replace(",", " "))
    st.dataframe(
        snapshot_results_to_dataframe(snapshot_results),
        width="stretch",
        hide_index=True,
        height=min(360, 80 + 35 * len(snapshot_results)),
    )
