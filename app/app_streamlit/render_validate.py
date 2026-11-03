# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from analyse_assets.validate_config import ValidationReport, validate_analyse_config
from app_proc.calculate_assets import evaluate_assets_file_for_ui
from app_proc.data_root import A_CONFIG_FILE_NAME
from app_streamlit.column_layout import amount_column_config, format_amount_columns
from importers.assets.data_model import AssetsDef
from importers.assets.read_assets import get_assets_file
from roi.config import get_config_file

_ASSETS_EVAL_DISPLAY = [
    AssetsDef.ID,
    AssetsDef.GROUP,
    AssetsDef.TYPE,
    AssetsDef.VALUE,
    AssetsDef.CURRENCY,
    AssetsDef.VALUE_PLN,
    AssetsDef.EVALUATION_DATE,
    AssetsDef.VALUE_DATE,
    AssetsDef.DAYS_AFTER_VALUATION,
    AssetsDef.LAST_TRANSACTION_DATE,
    AssetsDef.STATEMENT_DATE,
    AssetsDef.KIND,
]


def render_validate() -> None:
    st.subheader("Walidacja")
    _render_analyse_config_section()
    st.divider()
    _render_funding_section()
    st.divider()
    _render_assets_evaluation_section()


def _render_analyse_config_section() -> None:
    st.markdown(f"#### ROI w `{A_CONFIG_FILE_NAME}` (roi_def / roi_rules / roi_manual / instruments)")
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


def _render_funding_section() -> None:
    st.markdown("#### Funding cash-pool ↔ venue (Σ, bez korekty NAV)")
    st.caption(
        "Korytarze: Robo, DEGIRO/XTB (Revolut + mBank), Trade Republic, Revolut savings. "
        "Kolumny tx_a/tx_b = daty i kwoty legów. "
        "Mismatch = możliwy bias Σ majątku przy lukach wyciągów."
    )
    valuation_date = st.date_input(
        "Data wyceny (funding)",
        value=date.today(),
        key="validate_funding_valuation_date",
    )
    if st.button("Sprawdź funding", key="validate_funding_button"):
        try:
            from roi.funding_report import build_funding_report

            with st.spinner(f"Raport funding na {valuation_date:%Y-%m-%d}..."):
                report, warnings = build_funding_report(valuation_date)
            st.session_state["validate_funding_report"] = {
                "valuation_date": valuation_date.isoformat(),
                "result": report,
                "warnings": warnings,
            }
        except Exception as exc:
            st.error("Nie udało się zbudować raportu funding.")
            st.exception(exc)
            return

    payload = st.session_state.get("validate_funding_report")
    if payload is None:
        st.info("Kliknij przycisk, aby porównać Σ przepływów funding.")
        return

    result: pd.DataFrame = payload["result"]
    warnings: list[str] = payload["warnings"]
    n_mismatch = (
        int((result["status"] == "mismatch").sum()) if not result.empty else 0
    )
    n_error = int((result["status"] == "error").sum()) if not result.empty else 0
    n_b_only = int((result["status"] == "b_only").sum()) if not result.empty else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Korytarze", len(result))
    c2.metric("Mismatch", n_mismatch)
    c3.metric("B-only", n_b_only)
    c4.metric("Błędy", n_error)
    st.caption(f"Data wyceny: {payload['valuation_date']}")

    if n_error:
        st.error("Część korytarzy nie policzyła się (status=error).")
    elif n_mismatch:
        st.warning("Są niesparowane Σ funding (status=mismatch).")
    else:
        st.success("Brak mismatch — Σ korytarzy w tolerancji (Pekao B-only OK).")

    if warnings:
        st.dataframe(
            pd.DataFrame({"warning": warnings}),
            width="stretch",
            hide_index=True,
            height=min(220, 40 + 28 * len(warnings)),
        )

    if result.empty:
        return

    display = result.copy()
    for col in ("amount_a", "amount_b", "diff"):
        if col in display.columns:
            display[col] = pd.to_numeric(display[col], errors="coerce")
    st.dataframe(
        display,
        width="stretch",
        hide_index=True,
        height=min(420, 40 + 28 * max(len(display), 1)),
        column_config={
            "amount_a": st.column_config.NumberColumn(format="%.2f"),
            "amount_b": st.column_config.NumberColumn(format="%.2f"),
            "diff": st.column_config.NumberColumn(format="%.2f"),
        },
    )


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
    display = format_amount_columns(result[cols])
    st.dataframe(
        display,
        width="stretch",
        hide_index=True,
        height=420,
        column_config=amount_column_config(display),
    )


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
