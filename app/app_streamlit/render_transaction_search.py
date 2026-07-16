from __future__ import annotations

import pandas as pd
import streamlit as st

from app_proc.transaction_search import load_all_transactions, search_transactions


@st.cache_data(show_spinner="Wczytywanie transakcji...")
def _load_transactions_cached() -> pd.DataFrame:
    return load_all_transactions()


def render_transaction_search() -> None:
    st.subheader("Wyszukiwanie transakcji")

    try:
        transactions = _load_transactions_cached()
    except Exception as exc:
        st.error("Nie udalo sie wczytac transakcji.")
        st.exception(exc)
        return

    st.caption(
        f"Przeszukiwane zrodla: mBank i Revolut ({len(transactions):,} transakcji). "
        "Szukamy w polach: opis, tytul, kontrahent, konto."
    )

    query = st.text_input(
        "Szukaj",
        placeholder="np. nazwa kontrahenta, fragment tytulu, opis operacji...",
        key="transaction_search_query",
    )
    case_sensitive = st.checkbox("Uwzgledniaj wielkosc liter", value=False, key="transaction_search_case")

    col1, col2, col3 = st.columns(3)
    col1.metric("Wszystkie transakcje", f"{len(transactions):,}".replace(",", " "))
    col2.metric("Konta / zrodla", transactions["asset_id"].nunique() if not transactions.empty else 0)

    if not query.strip():
        st.info("Wpisz fraze wyszukiwania, aby zobaczyc pasujace transakcje.")
        return

    results = search_transactions(transactions, query, case_sensitive=case_sensitive)
    col3.metric("Wyniki", len(results))

    if results.empty:
        st.warning(f"Brak transakcji zawierajacych „{query}” w polach tekstowych.")
        return

    st.dataframe(results, width='stretch', hide_index=True, height=520)

    csv = results.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="Pobierz wyniki (CSV)",
        data=csv,
        file_name="transakcje_wyszukiwanie.csv",
        mime="text/csv",
        key="transaction_search_csv",
    )
