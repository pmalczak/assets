# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from analyse_assets.validate_config import ValidationReport, validate_analyse_config
from app_proc.calculate_assets import evaluate_assets_file_for_ui
from app_proc.data_root import A_CONFIG_FILE_NAME
from importers.assets.data_model import AssetsDef
from importers.assets.read_assets import get_assets_file
from roi.config import get_config_file

_ASSETS_EVAL_DISPLAY = [
    AssetsDef.ID,
    AssetsDef.GROUP,
    AssetsDef.TYPE,
    AssetsDef.CURRENCY,
    AssetsDef.VALUE,
    AssetsDef.VALUE_PLN,
    AssetsDef.EVALUATION_DATE,
    AssetsDef.VALUE_DATE,
    AssetsDef.DAYS_AFTER_VALUATION,
    AssetsDef.KIND,
]


def render_validate() -> None:
    st.subheader("Walidacja")
    _render_analyse_config_section()
    st.divider()
    _render_assets_evaluation_section()


def _render_analyse_config_section() -> None:
    st.markdown(f"#### ROI w `{A_CONFIG_FILE_NAME}` (roi_def / roi_rules / roi_manual)")
    config_path = get_config_file()
    st.caption(f"Plik: `{config_path}`")

    if st.button("Waliduj konfigurację ROI", key="validate_analyse_config_button"):
        try:
            with st.spinner("Walidacja arkuszy ROI..."):
                report = validate_analyse_config(config_path)
            st.session_state["validate_analyse_config_report"] = report
        except Exception as exc:
            st.error("Nie udało się zwalidować konfiguracji ROI.")
            st.exception(exc)
            return

    report: ValidationReport | None = st.session_state.get("validate_analyse_config_report")
    if report is None:
        st.info("Kliknij przycisk, aby uruchomić walidację konfiguracji.")
        return

    _render_report(report)


def _render_assets_evaluation_section() -> None:
    st.markdown(f"#### Ewaluacja katalogu `{A_CONFIG_FILE_NAME}` (arkusz assets)")
    try:
        assets_path = get_assets_file()
        st.caption(f"Plik: `{assets_path}`")
    except AssertionError as exc:
        st.error(str(exc))
        return

    valuation_date = st.date_input(
        "Data wyceny",
        value=date.today(),
        key="validate_assets_valuation_date",
    )

    if st.button("Ewaluuj assets", key="validate_assets_evaluate_button"):
        try:
            with st.spinner(f"Ewaluacja assets na {valuation_date:%Y-%m-%d}..."):
                evaluated, warnings = evaluate_assets_file_for_ui(valuation_date)
            st.session_state["validate_assets_evaluation"] = {
                "valuation_date": valuation_date.isoformat(),
                "result": evaluated,
                "warnings": warnings,
            }
        except Exception as exc:
            st.error("Nie udało się ewaluować assets_1.")
            st.exception(exc)
            return

    payload = st.session_state.get("validate_assets_evaluation")
    if payload is None:
        st.info("Kliknij przycisk, aby uruchomić ewaluację pliku assets.")
        return

    result: pd.DataFrame = payload["result"]
    warnings: list[str] = payload["warnings"]
    n_warn = len(warnings)
    total_pln = int(pd.to_numeric(result[AssetsDef.VALUE_PLN], errors="coerce").fillna(0).sum()) if not result.empty else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("Wiersze", len(result))
    c2.metric("Suma PLN", f"{total_pln:,}".replace(",", " "))
    c3.metric("Ostrzeżenia", n_warn)

    st.caption(f"Data wyceny: {payload['valuation_date']}")

    if n_warn:
        st.warning("Ostrzeżenia z ewaluacji:")
        st.dataframe(
            pd.DataFrame({"warning": warnings}),
            width="stretch",
            hide_index=True,
            height=min(220, 40 + 28 * n_warn),
        )
    elif result.empty:
        st.warning("Ewaluacja nie zwróciła żadnych wierszy.")
    else:
        st.success("Ewaluacja zakończona bez ostrzeżeń.")

    if result.empty:
        return

    cols = [c for c in _ASSETS_EVAL_DISPLAY if c in result.columns]
    st.dataframe(result[cols], width="stretch", hide_index=True, height=420)


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
