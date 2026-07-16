from __future__ import annotations

from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

from app_proc.calculate_assets import ASSETS_SNAPSHOT_STEP, PORTFOLIO_VALUATION_DATE
from app_proc.snapshots import snapshots_directory


def render_portfolio_history(history: pd.DataFrame, timeline_events: pd.DataFrame, latest_snapshot_date: date | None):
    st.subheader("Wartosc portfela (snapshoty)")

    if history.empty:
        st.warning(
            f"Brak snapshotow w katalogu `{snapshots_directory()}`. "
            "Uruchom `maintenance/recalculate_weekly_assets_snapshots.py`."
        )
        return

    available_groups = sorted(history["group"].dropna().unique().tolist())
    selected_groups = st.multiselect(
        "Widoczne grupy",
        options=available_groups,
        default=available_groups,
    )
    if not selected_groups:
        st.warning("Wybierz przynajmniej jedna grupe.")
        return

    visible_history = history[history["group"].isin(selected_groups)].copy()
    totals = visible_history.groupby("date", as_index=False)["value_pln"].sum().sort_values("date")
    current_value = float(totals["value_pln"].iloc[-1])
    start_value = float(totals["value_pln"].iloc[0])
    delta_value = current_value - start_value
    delta_pct = (delta_value / start_value * 100) if start_value else 0.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ostatni snapshot", f"{current_value:,.0f} PLN".replace(",", " "))
    c2.metric("Pierwszy w oknie", f"{start_value:,.0f} PLN".replace(",", " "))
    c3.metric("Zmiana w oknie", f"{delta_value:,.0f} PLN".replace(",", " "), f"{delta_pct:+.1f}%")
    if latest_snapshot_date:
        c4.metric("Data ostatniego snapshotu", latest_snapshot_date.isoformat())
    else:
        c4.metric("Data ostatniego snapshotu", "-")

    chart_data = (
        visible_history.groupby(["date", "group"], as_index=False)["value_pln"]
        .sum()
        .sort_values(["date", "group"])
    )
    month_lines = pd.DataFrame(
        {
            "date": pd.date_range(
                chart_data["date"].min().normalize(),
                chart_data["date"].max().normalize(),
                freq="MS",
            )
        }
    )

    area_chart = (
        alt.Chart(chart_data)
        .mark_area(interpolate="step-after")
        .encode(
            x=alt.X("date:T", title="Data"),
            y=alt.Y("value_pln:Q", title="Wartosc portfela (PLN)", stack="zero"),
            color=alt.Color("group:N", title="Grupa"),
            order=alt.Order("group:N"),
            tooltip=[
                alt.Tooltip("date:T", title="Data"),
                alt.Tooltip("group:N", title="Grupa"),
                alt.Tooltip("value_pln:Q", title="Wartosc", format=",.0f"),
            ],
        )
    )
    month_rules = (
        alt.Chart(month_lines)
        .mark_rule(color="#666666", strokeWidth=1, opacity=0.35)
        .encode(x="date:T")
    )
    chart = area_chart + month_rules

    if not timeline_events.empty:
        visible_events = timeline_events[
            (timeline_events["date"] >= chart_data["date"].min())
            & (timeline_events["date"] <= chart_data["date"].max())
        ].copy()

        if not visible_events.empty:
            totals_with_events = totals.rename(columns={"value_pln": "total_value_pln"})
            visible_events = visible_events.merge(totals_with_events, on="date", how="left")
            visible_events["total_value_pln"] = visible_events["total_value_pln"].ffill()
            visible_events["label_y"] = visible_events["total_value_pln"] * 1.01

            event_rules = (
                alt.Chart(visible_events)
                .mark_rule(color="#f4d03f", strokeWidth=2, opacity=0.7)
                .encode(
                    x="date:T",
                    tooltip=[alt.Tooltip("date:T", title="Data"), alt.Tooltip("label:N", title="Opis")],
                )
            )
            event_points = (
                alt.Chart(visible_events)
                .mark_point(color="#f4d03f", filled=True, size=90, shape="diamond")
                .encode(
                    x="date:T",
                    y=alt.Y("total_value_pln:Q"),
                    tooltip=[alt.Tooltip("date:T", title="Data"), alt.Tooltip("label:N", title="Opis")],
                )
            )
            event_labels = (
                alt.Chart(visible_events)
                .mark_text(color="#f4d03f", angle=325, align="left", baseline="bottom", dx=6, dy=-4, fontSize=11)
                .encode(
                    x="date:T",
                    y=alt.Y("label_y:Q"),
                    text="label:N",
                )
            )
            chart = chart + event_rules + event_points + event_labels

    st.altair_chart(chart, width='stretch')
    st.caption(
        f"Wykres budowany wylacznie ze snapshotow `{ASSETS_SNAPSHOT_STEP}` "
        f"(kolumna `{PORTFOLIO_VALUATION_DATE}`). Kazdy punkt to wartosc portfela "
        "wyliczona przez `calculate_assets()` na dana date wyceny — bez rekonstrukcji z transakcji."
    )
