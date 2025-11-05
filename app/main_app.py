import io
import pandas as pd
import streamlit as st
from pathlib import Path
import sys

project_root = Path().home() / r'PycharmProjects\github_common_py'
sys.path.append(str(project_root))

from importers.assets.data_model import AssetsFile, AssetsDef
from importers.assets.read_assets import read_assets
from check_wrong_catalogs import check_wrong_catalogs
from data_root import get_online_data_root
from data_step.data_step import DATA_STEP
from evaluators.evaluate_assets import evaluate_assets
from fx.data_model import LastFx
from nbp_fx_repo.nbp_fx_repository import NbpFxRepository, NBP_API_EUR

st.set_page_config(page_title="Assets Dashboard", layout="wide")

# ---- POMOCNICZE: KONFIGURACJA WYŚWIETLANIA KOLUMN LICZBOWYCH ----
def number_config(label: str, suffix: str | None = None):
    # Streamlit wyrównuje liczby do prawej, jeśli dtype jest liczbowy.
    # 'format' pozwala dołożyć sufiks waluty; tysięczne separatorem domyślnie brak.
    # (Jeśli bardzo potrzebujesz spacji jako separatorów tysięcy, napisz – dorzucę wariant z Styler+st.table.)
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

    assets = read_assets()
    check_wrong_catalogs(data_root, assets)
    assets = evaluate_assets(data_root, assets, fx_rates)

    assets = assets.sort_values(by=[AssetsFile.GROUP, AssetsFile.ID])
    assets = assets[assets[AssetsDef.VALUE] != 0]
    assets = assets.drop(columns=[AssetsDef.NOTES, LastFx.FX])

    # Zapis do Excela
    excel_buffer = io.BytesIO()
    assets.to_excel(excel_buffer, index=False)
    excel_buffer.seek(0)

    # --- Grupowania: liczby pozostają liczbami (klucz do prawego wyrównania) ---
    # 1) waluta + data + typ -> suma wartości (oryginalna waluta)
    g1 = (
        assets[[AssetsDef.TYPE, AssetsDef.CURRENCY, AssetsDef.EVALUATION_DATE, AssetsDef.VALUE]]
        .groupby([AssetsDef.CURRENCY, AssetsDef.EVALUATION_DATE, AssetsDef.TYPE], as_index=False)
        .sum(numeric_only=True)
        .round(0)
    )

    # 2) waluta + data + typ -> suma wartości PLN
    g2 = (
        assets[[AssetsDef.TYPE, AssetsDef.EVALUATION_DATE, AssetsDef.VALUE_PLN, AssetsDef.CURRENCY]]
        .groupby([AssetsDef.CURRENCY, AssetsDef.EVALUATION_DATE, AssetsDef.TYPE], as_index=False)
        .sum(numeric_only=True)
        .round(0)
    )

    # 3) grupa -> suma PLN (walutę zerujemy jak w Twoim kodzie; tu nie jest potrzebna)
    g3 = (
        assets[[AssetsDef.GROUP, AssetsDef.VALUE_PLN]]
        .groupby([AssetsDef.GROUP], as_index=False)
        .sum(numeric_only=True)
        .round(0)
    )

    # Upewnijmy się, że kolumny wartości są typu liczbowego (czasem po groupby bywa float)
    for col in [AssetsDef.VALUE, AssetsDef.VALUE_PLN]:
        if col in assets.columns and not pd.api.types.is_numeric_dtype(assets[col]):
            assets[col] = pd.to_numeric(assets[col], errors="coerce")
        for df in (g1, g2, g3):
            if col in df.columns and not pd.api.types.is_numeric_dtype(df[col]):
                df[col] = pd.to_numeric(df[col], errors="coerce")

    return {
        "assets": assets,
        "grouped_value_orig": g1,   # ma kolumnę waluty osobno
        "grouped_value_pln": g2,    # ma kolumnę waluty osobno
        "grouped_by_group_pln": g3, # bez waluty
        "excel_bytes": excel_buffer,
    }

def main():
    st.title("📊 Assets Dashboard")

    with st.spinner("Ładowanie i przetwarzanie danych..."):
        try:
            data = build_data()
        except Exception as e:
            st.error("Wystąpił błąd podczas przygotowywania danych.")
            st.exception(e)
            return

    # Pasek akcji
    left, right = st.columns([1, 1])
    with left:
        st.metric("Rekordy w assets", len(data["assets"]))
    with right:
        st.download_button(
            label="⬇️ Pobierz assets_evaluation.xlsx",
            data=data["excel_bytes"],
            file_name="assets_evaluation.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    tabs = st.tabs([
        "📄 Assets (raw)",
        "💱 Grupowanie: waluta + data + typ (wartość oryg.)",
        "🇵🇱 Grupowanie: waluta + data + typ (PLN)",
        "🧩 Grupowanie: grupa (PLN, sumy)",
    ])

    # 1) Assets (raw)
    with tabs[0]:
        st.subheader("Assets (po filtrach i bez kolumn: NOTES, FX)")
        st.dataframe(
            data["assets"],
            use_container_width=True,
            hide_index=True,
            column_config={
                AssetsDef.VALUE: number_config("Wartość (oryg.)"),
                AssetsDef.VALUE_PLN: number_config("Wartość (PLN)", "PLN"),
            },
        )

    # 2) Grupowanie w oryginalnej walucie
    with tabs[1]:
        st.subheader("Suma wartości wg waluty, daty i typu (wartość oryginalna)")
        st.dataframe(
            data["grouped_value_orig"],
            use_container_width=True,
            hide_index=True,
            column_config={
                AssetsDef.VALUE: number_config("Wartość (oryg.)"),
                # waluta jest osobną kolumną: AssetsDef.CURRENCY
            },
        )

    # 3) Grupowanie w PLN
    with tabs[2]:
        st.subheader("Suma wartości wg waluty, daty i typu (PLN)")
        st.dataframe(
            data["grouped_value_pln"],
            use_container_width=True,
            hide_index=True,
            column_config={
                AssetsDef.VALUE_PLN: number_config("Wartość (PLN)", "PLN"),
            },
        )

    # 4) Grupowanie po grupie (PLN)
    with tabs[3]:
        st.subheader("Suma wartości wg grupy (PLN)")
        st.dataframe(
            data["grouped_by_group_pln"],
            use_container_width=True,
            hide_index=True,
            column_config={
                AssetsDef.VALUE_PLN: number_config("Wartość (PLN)", "PLN"),
            },
        )

if __name__ == "__main__":
    pd.options.mode.copy_on_write = True
    pd.options.future.infer_string = True

    # Te opcje dotyczą tylko printów/konsoli — UI Streamlit jest niezależne:
    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    pd.set_option('display.colheader_justify', 'center')

    main()
