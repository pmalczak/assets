# -*- coding: utf-8 -*-
"""Workaroundy UI pod Python 3.14 + Streamlit/pyarrow (segfault bez tracebacku)."""
from __future__ import annotations

import pandas as pd
import streamlit as st


def dataframe_for_streamlit(df: pd.DataFrame) -> pd.DataFrame:
    """Ramka bez pandas StringDtype/bool — bezpieczniejsza dla serializacji Arrow."""
    if df is None or df.empty:
        return df
    out = df.copy()
    for col in out.columns:
        out[col] = out[col].map(lambda v: "" if v is None or (isinstance(v, float) and pd.isna(v)) else v)
        out[col] = out[col].astype(str)
    return out


def opt_in_download_button(
    *,
    prepare_label: str,
    prepare_key: str,
    button_label: str,
    data: bytes | None = None,
    data_factory=None,
    file_name: str,
    mime: str,
    download_key: str,
    disabled: bool = False,
    help_prepare: str | None = None,
) -> None:
    """Najpierw checkbox, potem pojedynczy download_button (bez rejestracji mediów na stałe).

    Podaj ``data`` albo ``data_factory`` (wywołane dopiero po włączeniu checkboxa).
    """
    if disabled:
        st.caption(f"{button_label} — brak danych.")
        return
    prepare = st.checkbox(
        prepare_label,
        value=False,
        key=prepare_key,
        help=help_prepare
        or "Na Python 3.14 rejestracja pliku w Streamlit bywa niestabilna — włącz tylko na czas pobrania.",
    )
    if not prepare:
        return
    payload = data_factory() if data_factory is not None else data
    if payload is None:
        st.caption(f"{button_label} — brak danych.")
        return
    st.download_button(
        label=button_label,
        data=payload,
        file_name=file_name,
        mime=mime,
        key=download_key,
    )
