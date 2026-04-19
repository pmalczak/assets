import io
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

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


def number_config(label: str, suffix: str | None = None):
    fmt = "%.0f" + (f" {suffix}" if suffix else "")
    return st.column_config.NumberColumn(label=label, format=fmt)


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

    excel_buffer = io.BytesIO()
    assets.to_excel(excel_buffer, index=False)
    excel_buffer.seek(0)

    g1 = (
        assets[[AssetsDef.TYPE, AssetsDef.CURRENCY, AssetsDef.EVALUATION_DATE, AssetsDef.VALUE]]
        .groupby([AssetsDef.CURRENCY, AssetsDef.EVALUATION_DATE, AssetsDef.TYPE], as_index=False)
        .sum(numeric_only=True)
        .round(0)
    )

    g2 = (
        assets[[AssetsDef.TYPE, AssetsDef.EVALUATION_DATE, AssetsDef.VALUE_PLN, AssetsDef.CURRENCY]]
        .groupby([AssetsDef.CURRENCY, AssetsDef.EVALUATION_DATE, AssetsDef.TYPE], as_index=False)
        .sum(numeric_only=True)
        .round(0)
    )

    g3 = (
        assets[[AssetsDef.GROUP, AssetsDef.VALUE_PLN]]
        .groupby([AssetsDef.GROUP], as_index=False)
        .sum(numeric_only=True)
        .round(0)
    )

    for col in [AssetsDef.VALUE, AssetsDef.VALUE_PLN]:
        if col in assets.columns and not pd.api.types.is_numeric_dtype(assets[col]):
            assets[col] = pd.to_numeric(assets[col], errors="coerce")
        for df in (g1, g2, g3):
            if col in df.columns and not pd.api.types.is_numeric_dtype(df[col]):
                df[col] = pd.to_numeric(df[col], errors="coerce")

    return {
        "assets": assets,
        "grouped_value_orig": g1,
        "grouped_value_pln": g2,
        "grouped_by_group_pln": g3,
        "excel_bytes": excel_buffer,
        "portfolio_history": history_data["history"],
        "history_skipped_assets": history_data["skipped_assets"],
    }


def render_portfolio_history(history: pd.DataFrame, skipped_assets: list[str]):
    st.subheader("Wartosc portfela za ostatni rok")

    if history.empty:
        st.warning("Brak danych historycznych do zbudowania wykresu portfela.")
    else:
        current_value = float(history["value_pln"].iloc[-1])
        start_value = float(history["value_pln"].iloc[0])
        delta_value = current_value - start_value

        c1, c2, c3 = st.columns(3)
        c1.metric("Biezaca wartosc", f"{current_value:,.0f} PLN".replace(",", " "))
        c2.metric("Zmiana 12M", f"{delta_value:,.0f} PLN".replace(",", " "))
        c3.metric("Poczatek zakresu", history["date"].iloc[0].strftime("%Y-%m-%d"))

        chart_data = history.rename(columns={"date": "Data", "value_pln": "Portfel PLN"})
        st.line_chart(chart_data, x="Data", y="Portfel PLN", use_container_width=True)

        st.caption(
            "Wykres jest odtwarzany z historii dostepnej w zrodlach danych i kursach NBP dla EUR. "
            "Jesli dla czesci aktywow nie ma historii, wykres pokazuje tylko obslugiwane serie."
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
        st.metric("Rekordy w assets", len(data["assets"]))
    with right:
        st.download_button(
            label="Pobierz assets_evaluation.xlsx",
            data=data["excel_bytes"],
            file_name="assets_evaluation.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    tabs = st.tabs(
        [
            "Portfolio 12M",
            "Assets (raw)",
            "Waluta + data + typ (orig.)",
            "Waluta + data + typ (PLN)",
            "Grupa (PLN)",
        ]
    )

    with tabs[0]:
        render_portfolio_history(data["portfolio_history"], data["history_skipped_assets"])

    with tabs[1]:
        st.subheader("Assets po filtrach i bez kolumn NOTES i FX")
        st.dataframe(
            data["assets"],
            use_container_width=True,
            hide_index=True,
            column_config={
                AssetsDef.VALUE: number_config("Wartosc (oryg.)"),
                AssetsDef.VALUE_PLN: number_config("Wartosc (PLN)", "PLN"),
            },
        )

    with tabs[2]:
        st.subheader("Suma wartosci wg waluty, daty i typu")
        st.dataframe(
            data["grouped_value_orig"],
            use_container_width=True,
            hide_index=True,
            column_config={
                AssetsDef.VALUE: number_config("Wartosc (oryg.)"),
            },
        )

    with tabs[3]:
        st.subheader("Suma wartosci wg waluty, daty i typu w PLN")
        st.dataframe(
            data["grouped_value_pln"],
            use_container_width=True,
            hide_index=True,
            column_config={
                AssetsDef.VALUE_PLN: number_config("Wartosc (PLN)", "PLN"),
            },
        )

    with tabs[4]:
        st.subheader("Suma wartosci wg grupy w PLN")
        st.dataframe(
            data["grouped_by_group_pln"],
            use_container_width=True,
            hide_index=True,
            column_config={
                AssetsDef.VALUE_PLN: number_config("Wartosc (PLN)", "PLN"),
            },
        )


if __name__ == "__main__":
    pd.options.mode.copy_on_write = True
    pd.options.future.infer_string = True
    main()
