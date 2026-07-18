from __future__ import annotations

import io
from datetime import date

import pandas as pd
import streamlit as st

from analyse_assets.account_tx import AccountTx
from analyse_assets.config_model import CONFIG_FILE_NAME
from analyse_assets.data_model import AssetRw
from app_proc.export_product_excel import MBANK_CONSOLIDATED_FILE
from evaluators.valuation_date import filter_excel_rows_on_or_before
from roi import CashFlowEvent, get_config_file, compute_portfolio_roi, load_unallocated_pool
from roi.allocate import normalize_whitespace

ROI_DISPLAY_COLUMNS = {
    "asset_id": "Aktywo",
    "capex": "Inwestycja (CAPEX)",
    "opex": "Wydatki (OPEX)",
    "revenue": "Wplywy (REVENUE)",
    "terminal_realized": "Zamkniecie (realiz.)",
    "terminal_unrealized": "Wycena (nerealiz.)",
    "roi_nominal": "ROI nominal",
    "xirr": "XIRR",
    "is_sold": "Sprzedane",
}
ROI_FLOW_DISPLAY_COLUMNS = {
    CashFlowEvent.DATE: "Data",
    CashFlowEvent.AMOUNT: "Kwota",
    CashFlowEvent.CATEGORY: "Kategoria",
    CashFlowEvent.SOURCE: "pool_id",
    CashFlowEvent.DESCRIPTION: "Typ operacji",
    CashFlowEvent.TITLE: "Tytul",
    CashFlowEvent.COUNTERPARTY: "Kontrahent",
    CashFlowEvent.ACCOUNT_NUMBER: "Numer konta",
}
UNALLOCATED_DISPLAY_COLUMNS = [
    AccountTx.POOL_ID,
    AccountTx.TRANSACTION_DATE,
    AssetRw.YEAR,
    AssetRw.MONTH,
    AssetRw.DAY,
    AccountTx.AMOUNT,
    AccountTx.OPERATION_TYPE,
    AccountTx.TITLE,
    AccountTx.COUNTERPARTY,
    AccountTx.ACCOUNT_NUMBER,
    AccountTx.ACCOUNT_ID,
]


def render_roi(default_valuation_date: date | None) -> None:
    st.subheader("ROI (nieruchomosci + cash)")

    valuation_date = st.date_input(
        "Data wyceny ROI",
        value=default_valuation_date or date.today(),
        key="roi_valuation_date",
    )

    info_col, _ = st.columns([3, 1])
    with info_col:
        st.caption(f"Konfiguracja: `{get_config_file()}`")

    try:
        with st.spinner("Liczenie ROI..."):
            summary, events_by_asset = compute_portfolio_roi(valuation_date)
    except Exception as exc:
        st.error("Nie udalo sie policzyc ROI.")
        st.exception(exc)
        return

    if summary.empty:
        st.info("Brak danych ROI w katalogu analyse_assets.")
        return

    st.caption(
        "ROI nominalny = suma alokowanych przeplywow + wycena z arkusza properties-wyceny dla otwartych inwestycji. "
        "XIRR = roczna stopa zwrotu z uwzglednieniem dat przeplywow i wyceny terminalnej na date wyceny. "
        "Cash (mbank_eur) liczony w EUR; nieruchomosci w PLN. "
        f"Zamkniecie: CLOSING w {CONFIG_FILE_NAME}."
    )

    total_roi = int(summary["roi_nominal"].sum())
    sold_count = int(summary["is_sold"].sum())
    c1, c2, c3 = st.columns(3)
    c1.metric("Liczba aktywow", len(summary))
    c2.metric("Sprzedane", sold_count)
    c3.metric("Suma ROI nominal", f"{total_roi:,}".replace(",", " "))

    display = summary[list(ROI_DISPLAY_COLUMNS.keys())].rename(columns=ROI_DISPLAY_COLUMNS)
    for col in ROI_DISPLAY_COLUMNS.values():
        if col in ("Sprzedane", "XIRR"):
            continue
        if col in display.columns:
            display[col] = display[col].map(
                lambda v: f"{v:,}".replace(",", " ") if isinstance(v, (int, float)) else v
            )
    if "XIRR" in display.columns:
        display["XIRR"] = summary["xirr"].map(
            lambda v: f"{v * 100:.1f}%" if v is not None and pd.notna(v) else "—"
        )

    st.dataframe(display, width='stretch', hide_index=True)

    csv = summary.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="Pobierz ROI (CSV)",
        data=csv,
        file_name=f"roi_{valuation_date:%Y-%m-%d}.csv",
        mime="text/csv",
        key="roi_csv_download",
    )

    unallocated = load_unallocated_pool(valuation_date)
    st.markdown("**Transakcje niezaalokowane (per pool_id)**")
    st.caption(
        "Konta ROR po usunieciu przeplywow wewnetrznych, "
        "bez wierszy przypisanych do inwestycji z analyse_assets_config. "
        "Produkty: `_unallocated_{pool_id}.parquet`."
    )
    st.caption(f"Liczba wierszy: {len(unallocated):,}".replace(",", " "))
    if unallocated.empty:
        st.info("Brak niezaalokowanych transakcji (wszystko przypisane do inwestycji).")
    else:
        preview = unallocated.copy()
        for column in (
            AccountTx.TITLE,
            AccountTx.COUNTERPARTY,
            AccountTx.OPERATION_TYPE,
            AccountTx.ACCOUNT_NUMBER,
        ):
            if column in preview.columns:
                preview[column] = preview[column].map(normalize_whitespace)
        display_columns = [column for column in UNALLOCATED_DISPLAY_COLUMNS if column in preview.columns]
        st.dataframe(preview[display_columns], width="stretch", hide_index=True, height=240)

        unallocated_export = preview[display_columns]
        unallocated_buffer = io.BytesIO()
        unallocated_export.to_excel(unallocated_buffer, index=False)
        st.download_button(
            label=f"Pobierz {MBANK_CONSOLIDATED_FILE}",
            data=unallocated_buffer.getvalue(),
            file_name=MBANK_CONSOLIDATED_FILE,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="roi_unallocated_xlsx",
        )

    warned = summary[summary["warnings"].astype(str).str.len() > 0]
    if not warned.empty:
        st.markdown("**Ostrzezenia**")
        st.dataframe(warned[["asset_id", "warnings"]], width='stretch', hide_index=True)

    st.markdown("**Szczegoly przeplywow**")
    asset_ids = sorted(summary["asset_id"].astype(str).tolist())
    selected_asset = st.selectbox("Aktywo", options=asset_ids, key="roi_selected_asset")
    events = events_by_asset.get(selected_asset, pd.DataFrame(columns=list(CashFlowEvent.COLUMN_ORDER)))
    if events.empty:
        st.info("Brak zarejestrowanych przeplywow dla tego aktywa.")
    else:
        events_display = filter_excel_rows_on_or_before(events, CashFlowEvent.DATE, valuation_date)
        flow_columns = [col for col in ROI_FLOW_DISPLAY_COLUMNS if col in events_display.columns]
        flow_display = events_display[flow_columns].rename(columns=ROI_FLOW_DISPLAY_COLUMNS)
        st.dataframe(flow_display, width='stretch', hide_index=True, height=280)
