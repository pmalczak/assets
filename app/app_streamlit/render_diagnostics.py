from __future__ import annotations

import streamlit as st


def render_diagnostics(data: dict[str, object]):
    st.divider()
    st.subheader("Diagnostyka snapshotow")

    summaries = data["snapshot_summaries"]
    history = data["history"]

    c1, c2, c3 = st.columns(3)
    c1.metric("Snapshotow w oknie", len(summaries))
    c2.metric("Punktow wykresu", len(history))
    c3.metric("Grup", history["group"].nunique() if not history.empty else 0)

    st.markdown(f"**Katalog:** `{data['snapshots_dir']}`")
    if summaries.empty:
        st.info("Brak plikow parquet w katalogu snapshotow.")

    st.markdown("**Ostatni snapshot per typ**")
    st.dataframe(
        data["snapshot_by_type"].sort_values("type"),
        width='stretch',
        hide_index=True,
    )
