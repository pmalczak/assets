# -*- coding: utf-8 -*-
from __future__ import annotations

import pandas as pd
import streamlit as st

from analyse_assets.config_model import CONFIG_FILE_NAME
from analyse_assets.validate_config import ValidationReport, validate_analyse_config
from roi.config import get_config_file


def render_validate() -> None:
    st.subheader("Walidacja")
    config_path = get_config_file()
    st.caption(f"Plik: `{config_path}` ({CONFIG_FILE_NAME})")

    if st.button("Waliduj analyse_assets_config", key="validate_analyse_config_button"):
        try:
            with st.spinner("Walidacja analyse_assets_config..."):
                report = validate_analyse_config(config_path)
            st.session_state["validate_analyse_config_report"] = report
        except Exception as exc:
            st.error("Nie udało się zwalidować analyse_assets_config.")
            st.exception(exc)
            return

    report: ValidationReport | None = st.session_state.get("validate_analyse_config_report")
    if report is None:
        st.info("Kliknij przycisk, aby uruchomić walidację.")
        return

    _render_report(report)


def _render_report(report: ValidationReport) -> None:
    n_err = len(report.errors)
    n_warn = len(report.warnings)
    c1, c2, c3 = st.columns(3)
    c1.metric("Błędy", n_err)
    c2.metric("Ostrzeżenia", n_warn)
    c3.metric("Status", "OK" if report.ok else "BŁĄD")

    if report.ok and not report.issues:
        st.success("OK — brak problemów.")
        return

    if report.ok:
        st.success("OK — brak błędów (są ostrzeżenia).")
    else:
        st.error(f"Walidacja nie przeszła: {n_err} błędów.")

    rows = [
        {
            "severity": issue.severity,
            "sheet": issue.sheet,
            "location": issue.location,
            "code": issue.code,
            "message": issue.message,
        }
        for issue in report.issues
    ]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=420)
