from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from app_proc.data_root import A_CONFIG_FILE_NAME
from app_proc.ui_prefs import current_sold_filter, filter_by_sold
from app_proc.export_product_excel import (
    list_roi_product_excel_files,
    roi_summary_excel_filename,
)
from app_streamlit.safe_download import dataframe_for_streamlit, opt_in_download_button
from evaluators.valuation_date import filter_excel_rows_on_or_before
from roi import CashFlowEvent, get_config_file, compute_portfolio_roi
from roi.broker_obligacje_roi import compute_obligacje_broker_roi
from roi.broker_trading_roi import compute_revolut_robo_ticker_roi
from roi.degiro_roi import compute_degiro_ticker_roi
from roi.mbank_deposit_roi import compute_mbank_deposit_roi
from roi.revolut_deposit_roi import compute_revolut_deposit_roi
from roi.xtb_roi import compute_xtb_ticker_roi

ROI_DISPLAY_COLUMNS = {
    "asset_id": "Aktywo",
    "capex": "Inwestycja (CAPEX)",
    "opex": "Wydatki (OPEX)",
    "revenue": "Wplywy (REVENUES)",
    "terminal_realized": "Dezynwestycja (realiz.)",
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


ROI_VENUE_CATALOG = "Katalog"
ROI_VENUE_ROBO = "Revolut robo"
ROI_VENUE_DEPOSITS = "Revolut depozyty"
ROI_VENUE_MBANK_DEPOSITS = "mBank depozyty"
ROI_VENUE_BONDS = "Obligacje"
ROI_VENUE_DEGIRO = "DEGIRO"
ROI_VENUE_XTB = "XTB"
ROI_VENUES = [
    ROI_VENUE_CATALOG,
    ROI_VENUE_ROBO,
    ROI_VENUE_DEPOSITS,
    ROI_VENUE_MBANK_DEPOSITS,
    ROI_VENUE_BONDS,
    ROI_VENUE_DEGIRO,
    ROI_VENUE_XTB,
]


def render_roi(default_valuation_date: date | None) -> None:
    st.subheader("ROI")
    st.caption(
        "Per miejsce inwestycji — operacje na koncie (XIRR tickera / aktywa). "
        "Wynik strategii GM (DEGIRO + XTB + złoto) jest w Portfele → 2 G-MOMENTUM; "
        "nie sumuj tych XIRR."
    )
    venue = st.pills(
        "Miejsce",
        options=ROI_VENUES,
        default=ROI_VENUE_CATALOG,
        required=True,
        key="roi_venue",
        width="stretch",
    )
    if venue == ROI_VENUE_CATALOG:
        _render_roi_catalog(default_valuation_date)
    elif venue == ROI_VENUE_ROBO:
        render_roi_revolut_robo(default_valuation_date)
    elif venue == ROI_VENUE_DEPOSITS:
        render_roi_revolut_deposits(default_valuation_date)
    elif venue == ROI_VENUE_MBANK_DEPOSITS:
        render_roi_mbank_deposits(default_valuation_date)
    elif venue == ROI_VENUE_BONDS:
        render_roi_obligacje(default_valuation_date)
    elif venue == ROI_VENUE_DEGIRO:
        render_roi_degiro(default_valuation_date)
    else:
        render_roi_xtb(default_valuation_date)


def _render_roi_catalog(default_valuation_date: date | None) -> None:
    st.subheader("ROI (nieruchomosci + cash + rocky-iv + zloto)")

    valuation_date = st.date_input(
        "Data wyceny ROI",
        value=default_valuation_date or date.today(),
        key="roi_valuation_date",
    )

    btn_col, info_col = st.columns([1, 3])
    with btn_col:
        recalculate = st.button(
            f"Przelicz ROI ({valuation_date:%Y-%m-%d})",
            key="recalculate_roi_button",
            type="primary",
            help="Przebudowuje cache DATA_STEP (10 roi) dla wybranej daty — alokacja CF + summary + Excel product.",
        )
    with info_col:
        st.caption(
            f"Konfiguracja: `{get_config_file()}`. "
            "Bez przycisku używany jest cache; przycisk wymusza pełne przeliczenie na wybraną datę."
        )

    if recalculate:
        try:
            with st.spinner(f"Przeliczanie ROI {valuation_date:%Y-%m-%d}..."):
                summary, events_by_asset = compute_portfolio_roi(
                    valuation_date,
                    force_read_all_data=True,
                )
            st.session_state["roi_last_recalculated"] = {
                "valuation_date": valuation_date.isoformat(),
                "assets": len(summary),
                "sold": int(summary["is_sold"].sum()) if not summary.empty and "is_sold" in summary else 0,
            }
            st.success(
                f"ROI {valuation_date:%Y-%m-%d}: {len(summary)} aktywów, "
                f"sprzedane {st.session_state['roi_last_recalculated']['sold']}."
            )
            st.rerun()
        except Exception as exc:
            st.error("Nie udało się przeliczyć ROI.")
            st.exception(exc)
            return

    last_recalc = st.session_state.get("roi_last_recalculated")
    if last_recalc:
        st.caption(
            f"Ostatnie wymuszone przeliczenie: {last_recalc['valuation_date']} "
            f"({last_recalc['assets']} aktywów)."
        )

    try:
        with st.spinner("Ładowanie ROI..."):
            summary, events_by_asset = compute_portfolio_roi(valuation_date)
    except Exception as exc:
        st.error("Nie udalo sie policzyc ROI.")
        st.exception(exc)
        summary = pd.DataFrame()
        events_by_asset = {}

    if summary.empty:
        st.info("Brak danych ROI w katalogu analyse_assets.")
        return

    st.caption(
        "ROI nominalny = suma alokowanych przeplywow + wycena z arkusza asset-evaluation dla otwartych inwestycji. "
        "XIRR = roczna stopa zwrotu z uwzglednieniem dat przeplywow i wyceny terminalnej na date wyceny. "
        "Cash (mbank_eur) liczony w EUR; nieruchomosci w PLN. "
        f"Dezynwestycja: DIVESTMENT w {A_CONFIG_FILE_NAME}; "
        "nieruchomosc: DIVESTMENT=sprzedane; brokerzy qty=0; cash=data zamkniecia manual."
    )

    summary = _apply_sold_filter(summary)
    if summary is None:
        _render_product_excel_downloads(valuation_date)
        return

    total_roi = int(summary["roi_nominal"].sum())
    sold_count = int(summary["is_sold"].sum())
    c1, c2, c3 = st.columns(3)
    c1.metric("Liczba aktywow", len(summary))
    c2.metric("Sprzedane", sold_count)
    c3.metric("Suma ROI nominal", f"{total_roi:,}".replace(",", " "))

    display = _format_roi_summary_display(summary)
    st.dataframe(dataframe_for_streamlit(display), width="stretch", hide_index=True)

    opt_in_download_button(
        prepare_label="Przygotuj pobieranie ROI (CSV)",
        prepare_key="prepare_roi_csv",
        button_label="Pobierz ROI (CSV)",
        data_factory=lambda: summary.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"roi_{valuation_date:%Y-%m-%d}.csv",
        mime="text/csv",
        download_key="roi_csv_download",
    )

    _render_product_excel_downloads(valuation_date)

    warned = summary[summary["warnings"].astype(str).str.len() > 0]
    if not warned.empty:
        st.markdown("**Ostrzezenia**")
        st.dataframe(
            dataframe_for_streamlit(warned[["asset_id", "warnings"]]),
            width="stretch",
            hide_index=True,
        )

    st.markdown("**Szczegoly przeplywow**")
    asset_ids = sorted(summary["asset_id"].astype(str).tolist())
    selected_asset = _asset_selectbox("Aktywo", asset_ids, "roi_selected_asset")
    events = events_by_asset.get(selected_asset, pd.DataFrame(columns=list(CashFlowEvent.COLUMN_ORDER)))
    if events.empty:
        st.info("Brak zarejestrowanych przeplywow dla tego aktywa.")
    else:
        flow_display = _prepare_flow_display(events, valuation_date)
        st.dataframe(
            dataframe_for_streamlit(flow_display),
            width="stretch",
            hide_index=True,
            height=280,
        )


def render_roi_revolut_robo(default_valuation_date: date | None) -> None:
    st.subheader("ROI Revolut robo (per ticker)")
    valuation_date = st.date_input(
        "Data wyceny ROI robo",
        value=default_valuation_date or date.today(),
        key="roi_robo_valuation_date",
    )
    st.caption(
        "Analityka z blottera `p_re_robo-trading` — osobno od syntetycznego wiersza "
        "`p_re_robo` w Wartość aktywów → Inwestycje. Terminal otwartych = last price × qty; "
        "sprzedane gdy qty=0. SELL → DIVESTMENT; DIVIDEND → REVENUES."
    )
    try:
        with st.spinner("Liczenie ROI robo ticker..."):
            summary, events_by_asset, warnings = compute_revolut_robo_ticker_roi(valuation_date)
    except Exception as exc:
        st.warning("Nie udało się policzyć ROI robo ticker.")
        st.exception(exc)
        return

    if warnings:
        for msg in warnings:
            st.warning(msg)

    if summary.empty:
        st.info("Brak transakcji trading dla p_re_robo.")
        return

    summary = _apply_sold_filter(summary)
    if summary is None:
        return

    st.dataframe(_format_roi_summary_display(summary), width="stretch", hide_index=True)

    asset_ids = sorted(summary["asset_id"].astype(str).tolist())
    selected = _asset_selectbox("Ticker (robo)", asset_ids, "roi_robo_selected_ticker")
    _render_flow_details(events_by_asset, selected, valuation_date, empty_msg="Brak przepływów dla tickera.")


def render_roi_revolut_deposits(default_valuation_date: date | None) -> None:
    st.subheader("ROI Revolut depozyty (savings)")
    valuation_date = st.date_input(
        "Data wyceny ROI depozytów",
        value=default_valuation_date or date.today(),
        key="roi_deposits_valuation_date",
    )
    st.caption(
        "Cashflow z `savings-statement`: Depozyt → CAPEX (−); Wypłata → DIVESTMENT (+). "
        "Oprocentowanie brutto poza CF (w Saldo/terminalu). "
        "Zobowiązanie podatkowe 19% (rok wyceny) jako osobne aktywo."
    )
    try:
        with st.spinner("Liczenie ROI depozytów Revolut..."):
            summary, events_by_asset, warnings = compute_revolut_deposit_roi(valuation_date)
    except Exception as exc:
        st.warning("Nie udało się policzyć ROI depozytów Revolut.")
        st.exception(exc)
        return

    if warnings:
        for msg in warnings:
            st.warning(msg)

    if summary.empty:
        st.info("Brak danych savings-statement dla p_re_* / g_re_*.")
        return

    summary = _apply_sold_filter(summary)
    if summary is None:
        return

    st.dataframe(_format_roi_summary_display(summary), width="stretch", hide_index=True)

    asset_ids = sorted(summary["asset_id"].astype(str).tolist())
    selected = _asset_selectbox("Depozyt", asset_ids, "roi_deposits_selected_asset")
    _render_flow_details(
        events_by_asset,
        selected,
        valuation_date,
        empty_msg="Brak przepływów dla depozytu.",
    )


def render_roi_mbank_deposits(default_valuation_date: date | None) -> None:
    st.subheader("ROI mBank depozyty (per NR)")
    valuation_date = st.date_input(
        "Data wyceny ROI lokat mBank",
        value=default_valuation_date or date.today(),
        key="roi_mbank_deposits_valuation_date",
    )
    st.caption(
        "Cashflow z wyciągu ROR per `NR` w tytule: `OTW. LOKATY` → CAPEX; "
        "zerwanie/wygaśnięcie → DIVESTMENT (kapitał); odsetki → REVENUES; "
        "podatek z NR → OPEX. Terminal otwartej = kapitał (−CAPEX); "
        "DIVESTMENT zamyka lokatę (terminal 0). Snapshot NAV bez zmian w v1."
    )
    try:
        with st.spinner("Liczenie ROI lokat mBank..."):
            summary, events_by_asset, warnings = compute_mbank_deposit_roi(valuation_date)
    except Exception as exc:
        st.warning("Nie udało się policzyć ROI lokat mBank.")
        st.exception(exc)
        return

    if warnings:
        for msg in warnings:
            st.warning(msg)

    if summary.empty:
        st.info("Brak lokat mBank (`OTW. LOKATY NR` / operacje lokat z NR) w wyciągach.")
        return

    summary = _apply_sold_filter(summary)
    if summary is None:
        return

    st.dataframe(_format_roi_summary_display(summary), width="stretch", hide_index=True)

    asset_ids = sorted(summary["asset_id"].astype(str).tolist())
    selected = _asset_selectbox("Lokata (NR)", asset_ids, "roi_mbank_deposits_selected_asset")
    _render_flow_details(
        events_by_asset,
        selected,
        valuation_date,
        empty_msg="Brak przepływów dla lokaty.",
    )


def render_roi_obligacje(default_valuation_date: date | None) -> None:
    st.subheader("ROI obligacje skarbowe (per kod)")
    valuation_date = st.date_input(
        "Data wyceny ROI obligacji",
        value=default_valuation_date or date.today(),
        key="roi_bonds_valuation_date",
    )
    st.caption(
        "Analityka z rejestru przepływy pieniężne (HistoriaDyspozycji) — osobno od "
        "syntetycznego wiersza `obligacjeskarbowe` (MTM ze stanu). "
        "Mapowanie CF: zakup → CAPEX; wypłata → DIVESTMENT; opłata → OPEX. "
        "Naliczenia/odsetki/podatek poza ROI (w MTM). Terminal = WARTOŚĆ AKTUALNA; sprzedane gdy qty=0."
    )
    try:
        with st.spinner("Liczenie ROI obligacji..."):
            summary, events_by_asset, warnings = compute_obligacje_broker_roi(valuation_date)
    except Exception as exc:
        st.warning("Nie udało się policzyć ROI obligacji skarbowych.")
        st.exception(exc)
        return

    if warnings:
        for msg in warnings:
            st.warning(msg)

    if summary.empty:
        st.info("Brak danych historii/stanu dla obligacjeskarbowe.")
        return

    summary = _apply_sold_filter(summary)
    if summary is None:
        return

    st.dataframe(_format_roi_summary_display(summary), width="stretch", hide_index=True)

    asset_ids = sorted(summary["asset_id"].astype(str).tolist())
    selected = _asset_selectbox("Kod obligacji", asset_ids, "roi_bonds_selected_code")
    _render_flow_details(events_by_asset, selected, valuation_date, empty_msg="Brak przepływów dla kodu.")


def render_roi_degiro(default_valuation_date: date | None) -> None:
    st.subheader("ROI DEGIRO (per ISIN)")
    valuation_date = st.date_input(
        "Data wyceny ROI DEGIRO",
        value=default_valuation_date or date.today(),
        key="roi_degiro_valuation_date",
    )
    st.caption(
        "Analityka z pakietów DEGIRO: Transactions → CAPEX/DIVESTMENT, "
        "Account: Dywidenda → REVENUES. Terminal otwartych = Wartość w EUR "
        "z najnowszego Portfolio <= data wyceny; opłaty/podatki/FX poza XIRR v1."
    )
    try:
        with st.spinner("Liczenie ROI DEGIRO..."):
            summary, events_by_asset, warnings = compute_degiro_ticker_roi(valuation_date)
    except Exception as exc:
        st.warning("Nie udało się policzyć ROI DEGIRO.")
        st.exception(exc)
        return

    if warnings:
        for msg in warnings:
            st.warning(msg)

    if summary.empty:
        st.info("Brak danych DEGIRO dla p_degiro.")
        return

    summary = _apply_sold_filter(summary)
    if summary is None:
        return

    st.dataframe(_format_roi_summary_display(summary), width="stretch", hide_index=True)

    asset_ids = sorted(summary["asset_id"].astype(str).tolist())
    selected = _asset_selectbox("ISIN (DEGIRO)", asset_ids, "roi_degiro_selected_isin")
    _render_flow_details(events_by_asset, selected, valuation_date, empty_msg="Brak przepływów dla ISIN.")


def render_roi_xtb(default_valuation_date: date | None) -> None:
    st.subheader("ROI XTB (per ticker)")
    valuation_date = st.date_input(
        "Data wyceny ROI XTB",
        value=default_valuation_date or date.today(),
        key="roi_xtb_valuation_date",
    )
    st.caption(
        "Analityka z DATA_STEP (`p_xtb-cash`): Cash Operations → CAPEX/DIVESTMENT/REVENUES. "
        "Terminal otwartych = Value z najnowszego Open Positions <= data wyceny. "
        "Wpłaty/wypłaty/prowizje/podatki/FX poza XIRR per instrument (jak DEGIRO v1)."
    )
    try:
        with st.spinner("Liczenie ROI XTB..."):
            summary, events_by_asset, warnings = compute_xtb_ticker_roi(valuation_date)
    except Exception as exc:
        st.warning("Nie udało się policzyć ROI XTB.")
        st.exception(exc)
        return

    if warnings:
        for msg in warnings:
            st.warning(msg)

    if summary.empty:
        st.info("Brak danych XTB dla p_xtb.")
        return

    summary = _apply_sold_filter(summary)
    if summary is None:
        return

    st.dataframe(_format_roi_summary_display(summary), width="stretch", hide_index=True)

    asset_ids = sorted(summary["asset_id"].astype(str).tolist())
    selected = _asset_selectbox("Ticker (XTB)", asset_ids, "roi_xtb_selected_ticker")
    _render_flow_details(events_by_asset, selected, valuation_date, empty_msg="Brak przepływów dla tickera.")


def _apply_sold_filter(summary: pd.DataFrame) -> pd.DataFrame | None:
    mode = current_sold_filter()
    filtered = filter_by_sold(summary, mode)
    if filtered.empty:
        st.info(f"Brak pozycji dla filtra: {mode}.")
        return None
    return filtered


def _asset_selectbox(label: str, asset_ids: list[str], key: str) -> str:
    if key in st.session_state and st.session_state[key] not in asset_ids:
        del st.session_state[key]
    return st.selectbox(label, options=asset_ids, key=key)


def _prepare_flow_display(events: pd.DataFrame, valuation_date: date) -> pd.DataFrame:
    events_display = filter_excel_rows_on_or_before(events, CashFlowEvent.DATE, valuation_date)
    if not events_display.empty and CashFlowEvent.DATE in events_display.columns:
        events_display = events_display.copy()
        events_display["_sort"] = pd.to_datetime(events_display[CashFlowEvent.DATE], errors="coerce")
        events_display = events_display.sort_values(
            "_sort",
            ascending=False,
            na_position="last",
            kind="mergesort",
        ).drop(columns=["_sort"])
    flow_columns = [col for col in ROI_FLOW_DISPLAY_COLUMNS if col in events_display.columns]
    return events_display[flow_columns].rename(columns=ROI_FLOW_DISPLAY_COLUMNS)


def _format_roi_summary_display(summary: pd.DataFrame) -> pd.DataFrame:
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
    if "Sprzedane" in display.columns:
        # bool + pyarrow na Python 3.14 potrafi zabić proces Streamlit (segfault).
        display["Sprzedane"] = summary["is_sold"].map(lambda v: "tak" if bool(v) else "nie")
    return display


def _render_flow_details(
    events_by_asset: dict[str, pd.DataFrame],
    selected: str,
    valuation_date: date,
    *,
    empty_msg: str,
) -> None:
    events = events_by_asset.get(selected, pd.DataFrame(columns=list(CashFlowEvent.COLUMN_ORDER)))
    if events.empty:
        st.info(empty_msg)
        return
    events_display = _prepare_flow_display(events, valuation_date)
    st.dataframe(events_display, width="stretch", hide_index=True, height=220)


def _render_product_excel_downloads(valuation_date: date) -> None:
    st.markdown("**Pliki Excel (product)**")
    st.caption(
        f"Katalog `INWESTYCJE/product/{valuation_date:%Y-%m-%d}/` — "
        f"`{roi_summary_excel_filename(valuation_date)}`, "
        "`unallocated_{pool_id}.xlsx`, per-asset `mbank_*.xlsx`. "
        "Jeden plik naraz (wiele równoległych download_button + pyarrow bywa niestabilne na Python 3.14)."
    )
    files = list_roi_product_excel_files(valuation_date)
    if not files:
        st.caption("Brak plikow Excel — wygeneruj ROI (alokacja) lub sprawdz katalog product.")
        return

    key_prefix = f"roi_xlsx_{valuation_date:%Y%m%d}"
    names = [path.name for path in files]
    selected_name = st.selectbox("Plik do pobrania", options=names, key=f"{key_prefix}_pick")
    path = next(path for path in files if path.name == selected_name)
    if not path.is_file():
        st.caption(f"Brak pliku: `{path.name}`")
        return
    opt_in_download_button(
        prepare_label=f"Przygotuj pobieranie `{selected_name}`",
        prepare_key=f"{key_prefix}_prepare",
        button_label=f"Pobierz {path.name}",
        data_factory=path.read_bytes,
        file_name=path.name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        download_key=f"{key_prefix}_{path.name}",
    )
