import io
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
import altair as alt

project_root = Path().home() / r"PycharmProjects\github_common_py"
sys.path.append(str(project_root))

from check_wrong_catalogs import check_wrong_catalogs
from data_root import get_online_data_root
from data_step.data_step import DATA_STEP
from evaluators.evaluate_assets import evaluate_assets
from fx.data_model import LastFx
from importers.assets.data_model import AssetsDef, AssetsFile
from importers.assets.read_assets import read_assets
from nbp_fx_repo.nbp_fx_repository import NBP_API_EUR, NbpFxRepository
from portfolio_history import build_portfolio_history

st.set_page_config(page_title="Assets Dashboard", layout="wide")


def build_data():
    local_data_steps_root = Path(__file__).parent.parent
    DATA_STEP.init_steps(root=local_data_steps_root)

    data_root = get_online_data_root()

    metadata_root: Path = DATA_STEP.metadata.get_metadata_root() / "fx"
    metadata_root.mkdir(parents=True, exist_ok=True)

    fx_repo = NbpFxRepository(target_directory=metadata_root, min_year=2005)
    fx_rates = fx_repo.update_to_date()
    fx_rates = fx_rates[[NBP_API_EUR]]

    assets_catalog = read_assets()
    check_wrong_catalogs(data_root, assets_catalog)
    history_data = build_portfolio_history(assets_catalog, fx_rates)

    assets = evaluate_assets(data_root, assets_catalog, fx_rates)
    assets = assets.sort_values(by=[AssetsFile.GROUP, AssetsFile.ID])
    assets = assets[assets[AssetsDef.VALUE] != 0]
    assets = assets.drop(columns=[AssetsDef.NOTES, LastFx.FX])
    snapshot_by_group = (
        assets[[AssetsDef.GROUP, AssetsDef.VALUE_PLN]]
        .assign(**{AssetsDef.VALUE_PLN: pd.to_numeric(assets[AssetsDef.VALUE_PLN], errors="coerce").fillna(0)})
        .groupby(AssetsDef.GROUP, as_index=False)[AssetsDef.VALUE_PLN]
        .sum()
        .rename(columns={AssetsDef.GROUP: "group", AssetsDef.VALUE_PLN: "value_pln"})
    )
    snapshot_total_pln = float(snapshot_by_group["value_pln"].sum())
    history = _align_history_to_snapshot(history_data["history"], snapshot_by_group)

    excel_buffer = io.BytesIO()
    assets.to_excel(excel_buffer, index=False)
    excel_buffer.seek(0)

    return {
        "excel_bytes": excel_buffer,
        "portfolio_history": history,
        "history_skipped_assets": history_data["skipped_assets"],
        "snapshot_total_pln": snapshot_total_pln,
    }


def _align_history_to_snapshot(history: pd.DataFrame, snapshot_by_group: pd.DataFrame) -> pd.DataFrame:
    aligned = history.copy()
    today = pd.Timestamp.today().normalize()

    if aligned.empty:
        fallback = snapshot_by_group.copy()
        fallback["date"] = today
        return fallback[["date", "group", "value_pln"]]

    aligned["date"] = pd.to_datetime(aligned["date"])
    aligned = aligned.sort_values("date").reset_index(drop=True)
    aligned["value_pln"] = pd.to_numeric(aligned["value_pln"], errors="coerce").fillna(0)

    last_date = aligned["date"].max()
    last_history_by_group = (
        aligned[aligned["date"] == last_date][["group", "value_pln"]]
        .groupby("group", as_index=False)["value_pln"]
        .sum()
        .rename(columns={"value_pln": "history_value_pln"})
    )

    offsets = snapshot_by_group.merge(last_history_by_group, on="group", how="outer").fillna(0)
    offsets["missing_constant_value"] = offsets["value_pln"] - offsets["history_value_pln"]

    aligned = aligned.merge(offsets[["group", "missing_constant_value"]], on="group", how="left")
    aligned["missing_constant_value"] = aligned["missing_constant_value"].fillna(0)
    aligned["value_pln"] = aligned["value_pln"] + aligned["missing_constant_value"]
    aligned = aligned.drop(columns=["missing_constant_value"])

    if last_date != today:
        last_visible = (
            aligned[aligned["date"] == last_date][["group", "value_pln"]]
            .groupby("group", as_index=False)["value_pln"]
            .sum()
        )
        last_visible["date"] = today
        aligned = pd.concat([aligned, last_visible[["date", "group", "value_pln"]]], ignore_index=True)
    else:
        aligned = aligned.merge(snapshot_by_group, on="group", how="left", suffixes=("", "_snapshot"))
        aligned["value_pln"] = aligned["value_pln_snapshot"].fillna(aligned["value_pln"])
        aligned = aligned.drop(columns=["value_pln_snapshot"])

    return aligned.sort_values(["date", "group"]).reset_index(drop=True)


def render_portfolio_history(history: pd.DataFrame, skipped_assets: list[str]):
    st.subheader("Wartosc portfela za ostatni rok")

    if history.empty:
        st.warning("Brak danych historycznych do zbudowania wykresu portfela.")
    else:
        totals = history.groupby("date", as_index=False)["value_pln"].sum().sort_values("date")
        current_value = float(totals["value_pln"].iloc[-1])
        start_value = float(totals["value_pln"].iloc[0])
        delta_value = current_value - start_value

        c1, c2, c3 = st.columns(3)
        c1.metric("Biezaca wartosc", f"{current_value:,.0f} PLN".replace(",", " "))
        c2.metric("Zmiana 12M", f"{delta_value:,.0f} PLN".replace(",", " "))
        c3.metric("Poczatek zakresu", totals["date"].iloc[0].strftime("%Y-%m-%d"))

        chart_data = (
            history.groupby(["date", "group"], as_index=False)["value_pln"]
            .sum()
            .sort_values(["date", "group"])
        )
        chart = (
            alt.Chart(chart_data)
            .mark_area()
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
        st.altair_chart(chart, use_container_width=True)

        st.caption(
            "Historia jest odtwarzana z danych zrodlowych i kursow NBP dla EUR. "
            "Aktywa bez szeregow czasowych sa doliczane jako stala wartosc w calym zakresie 12M, per grupa."
        )

    if skipped_assets:
        st.info(
            "Pominiete lub niepelne zrodla historii: "
            + ", ".join(skipped_assets[:8])
            + (" ..." if len(skipped_assets) > 8 else "")
        )


def main():
    st.title("Assets Dashboard")

    with st.spinner("Ladowanie i przetwarzanie danych..."):
        try:
            data = build_data()
        except Exception as e:
            st.error("Wystapil blad podczas przygotowywania danych.")
            st.exception(e)
            return

    left, right = st.columns([1, 1])
    with left:
        st.metric("Biezacy snapshot", f"{data['snapshot_total_pln']:,.0f} PLN".replace(",", " "))
    with right:
        st.download_button(
            label="Pobierz assets_evaluation.xlsx",
            data=data["excel_bytes"],
            file_name="assets_evaluation.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    render_portfolio_history(data["portfolio_history"], data["history_skipped_assets"])


if __name__ == "__main__":
    pd.options.mode.copy_on_write = True
    pd.options.future.infer_string = True
    main()
