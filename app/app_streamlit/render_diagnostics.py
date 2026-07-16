from __future__ import annotations

from datetime import date

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
    st.markdown("**Lista snapshotow**")
    if summaries.empty:
        st.info("Brak plikow parquet w katalogu snapshotow.")
    else:
        display = summaries.copy()
        display["date"] = display["date"].apply(lambda d: d.isoformat() if isinstance(d, date) else d)
        st.dataframe(display.sort_values("date"), width='stretch', hide_index=True)

    st.markdown("**Ostatni snapshot per grupa**")
    st.dataframe(
        data["snapshot_by_group"].sort_values("group"),
        width='stretch',
        hide_index=True,
    )

    st.markdown("**Historia per grupa (z snapshotow)**")
    st.dataframe(
        history.sort_values(["date", "group"]),
        width='stretch',
        hide_index=True,
        height=280,
    )
