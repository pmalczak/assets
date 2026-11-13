# -*- coding: utf-8 -*-
"""Zakładka Walidacja CF — funding cash-pool ↔ venue."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from roi.funding_report import (
    MATCH_KIND_A_ONLY,
    MATCH_KIND_B_ONLY,
    MATCH_KIND_EXACT,
    MATCH_KIND_SETTLEMENT,
    MATCH_SETTLEMENT_DAYS,
    RECONCILE_TOLERANCE_EUR,
    RECONCILE_TOLERANCE_PLN,
    STATUS_B_ONLY,
    STATUS_ERROR,
    STATUS_MISMATCH,
    STATUS_OK,
    build_funding_report,
    matched_legs_frame,
)

_CORRIDOR_LABELS = {
    "robo": "Robo (Revolut EUR ↔ TOP-UP)",
    "degiro_revolut": "DEGIRO Revolut EUR",
    "degiro_mbank": "DEGIRO mBank PLN",
    "xtb_adyen": "XTB Adyen (Revolut PLN)",
    "xtb_mbank": "XTB mBank",
    "traderepublic": "Trade Republic",
}

_STATUS_LABELS = {
    STATUS_OK: "OK",
    STATUS_MISMATCH: "Niezgodność",
    STATUS_B_ONLY: "Tylko strona B",
    STATUS_ERROR: "Błąd",
}

_SUMMARY_COLUMNS = [
    "Korytarz",
    "Waluta",
    "Strona A",
    "Σ A",
    "Strona B",
    "Σ B",
    "Δ",
    "Status",
    "Uwagi",
]

_MATCH_LABELS = {
    MATCH_KIND_EXACT: "Zgodne",
    MATCH_KIND_SETTLEMENT: "Rozliczenie",
    MATCH_KIND_A_ONLY: "Tylko A",
    MATCH_KIND_B_ONLY: "Tylko B",
}

_DETAILS_COLUMNS = [
    "Data A",
    "Kwota A",
    "Data B",
    "Kwota B",
    "Δ dni",
    "Match",
]


@st.cache_data(show_spinner="Raport funding…")
def _load_funding_report(valuation_date: date) -> tuple[pd.DataFrame, tuple[str, ...]]:
    report, warnings = build_funding_report(valuation_date)
    return report, tuple(warnings)


def _corridor_label(corridor: str) -> str:
    if corridor in _CORRIDOR_LABELS:
        return _CORRIDOR_LABELS[corridor]
    if corridor.startswith("savings_deposit:"):
        return f"Savings depozyt ({corridor.split(':', 1)[1]})"
    if corridor.startswith("savings_withdraw:"):
        return f"Savings wypłata ({corridor.split(':', 1)[1]})"
    return corridor


def _status_label(status: str) -> str:
    return _STATUS_LABELS.get(str(status), str(status))


def _summary_frame(result: pd.DataFrame) -> pd.DataFrame:
    if result.empty:
        return pd.DataFrame(columns=_SUMMARY_COLUMNS)
    rows = []
    for _, row in result.iterrows():
        rows.append(
            {
                "Korytarz": _corridor_label(str(row["corridor"])),
                "Waluta": row.get("currency", ""),
                "Strona A": row.get("side_a", ""),
                "Σ A": pd.to_numeric(row.get("amount_a"), errors="coerce"),
                "Strona B": row.get("side_b", ""),
                "Σ B": pd.to_numeric(row.get("amount_b"), errors="coerce"),
                "Δ": pd.to_numeric(row.get("diff"), errors="coerce"),
                "Status": _status_label(str(row.get("status", ""))),
                "Uwagi": row.get("detail", "") or "",
            }
        )
    return pd.DataFrame(rows, columns=_SUMMARY_COLUMNS)


def _amount_tolerance(currency: object) -> float:
    if str(currency or "").strip().upper() == "EUR":
        return RECONCILE_TOLERANCE_EUR
    return RECONCILE_TOLERANCE_PLN


def _details_frame(row: pd.Series) -> pd.DataFrame:
    matched = matched_legs_frame(
        str(row.get("tx_a", "") or ""),
        str(row.get("tx_b", "") or ""),
        amount_tolerance=_amount_tolerance(row.get("currency")),
        max_date_skew_days=MATCH_SETTLEMENT_DAYS,
    )
    if matched.empty:
        return pd.DataFrame(columns=_DETAILS_COLUMNS)
    rows = []
    for _, leg in matched.iterrows():
        skew = leg.get("date_skew_days")
        rows.append(
            {
                "Data A": leg.get("date_a") or "",
                "Kwota A": leg.get("amount_a"),
                "Data B": leg.get("date_b") or "",
                "Kwota B": leg.get("amount_b"),
                "Δ dni": "" if skew is None or (isinstance(skew, float) and pd.isna(skew)) else int(skew),
                "Match": _MATCH_LABELS.get(str(leg.get("match", "")), str(leg.get("match", ""))),
            }
        )
    return pd.DataFrame(rows, columns=_DETAILS_COLUMNS)


def _default_corridor_index(result: pd.DataFrame) -> int:
    if result.empty:
        return 0
    statuses = result["status"].astype(str).tolist()
    for prefer in (STATUS_ERROR, STATUS_MISMATCH, STATUS_B_ONLY):
        for i, status in enumerate(statuses):
            if status == prefer:
                return i
    return 0


def render_validate_cf() -> None:
    st.subheader("Walidacja CF")
    st.caption(
        "Funding cash-pool ↔ venue (Σ, bez korekty NAV). "
        "Korytarze: Robo, DEGIRO/XTB (Revolut + mBank), Trade Republic, Revolut savings. "
        "Mismatch = możliwy bias Σ majątku przy lukach wyciągów."
    )
    valuation_date = st.date_input(
        "Data wyceny",
        value=date.today(),
        key="validate_funding_valuation_date",
    )

    try:
        result, warnings = _load_funding_report(valuation_date)
    except Exception as exc:
        st.error("Nie udało się zbudować raportu funding.")
        st.exception(exc)
        return

    warnings_list = list(warnings)
    n_mismatch = (
        int((result["status"] == STATUS_MISMATCH).sum()) if not result.empty else 0
    )
    n_error = int((result["status"] == STATUS_ERROR).sum()) if not result.empty else 0
    n_b_only = int((result["status"] == STATUS_B_ONLY).sum()) if not result.empty else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Korytarze", len(result))
    c2.metric("Niezgodności", n_mismatch)
    c3.metric("Tylko B", n_b_only)
    c4.metric("Błędy", n_error)

    if n_error:
        st.error("Część korytarzy nie policzyła się (status=błąd).")
    elif n_mismatch:
        st.warning("Są niesparowane Σ funding (status=niezgodność).")
    else:
        st.success("Brak niezgodności — Σ korytarzy w tolerancji.")

    if warnings_list:
        st.dataframe(
            pd.DataFrame({"Ostrzeżenie": warnings_list}),
            width="stretch",
            hide_index=True,
            height=min(220, 40 + 28 * len(warnings_list)),
        )

    if result.empty:
        st.info("Brak korytarzy do wyświetlenia.")
        return

    summary = _summary_frame(result)
    st.markdown("#### Korytarze")
    st.dataframe(
        summary,
        width="stretch",
        hide_index=True,
        height=min(420, 40 + 28 * max(len(summary), 1)),
        column_config={
            "Σ A": st.column_config.NumberColumn(format="%.2f"),
            "Σ B": st.column_config.NumberColumn(format="%.2f"),
            "Δ": st.column_config.NumberColumn(format="%.2f"),
        },
    )

    corridor_ids = [str(c) for c in result["corridor"].tolist()]
    default_idx = _default_corridor_index(result)
    chosen_id = st.selectbox(
        "Korytarz — szczegóły transakcji",
        options=corridor_ids,
        index=min(default_idx, len(corridor_ids) - 1),
        format_func=_corridor_label,
        key=f"validate_funding_corridor_{valuation_date.isoformat()}",
    )
    selected = result.loc[result["corridor"].astype(str) == chosen_id].iloc[0]

    details = _details_frame(selected)
    st.markdown("#### Transakcje korytarza")
    st.caption(
        f"A: `{selected.get('side_a', '')}` · B: `{selected.get('side_b', '')}` · "
        f"sparowanie: waluta + kwota, data ta sama albo Δ≤{MATCH_SETTLEMENT_DAYS} dni (rozliczenie)."
    )
    if details.empty:
        st.info("Brak transakcji w wybranym korytarzu.")
        return
    st.dataframe(
        details,
        width="stretch",
        hide_index=True,
        height=min(420, 40 + 28 * max(len(details), 1)),
        column_config={
            "Kwota A": st.column_config.NumberColumn(format="%.2f"),
            "Kwota B": st.column_config.NumberColumn(format="%.2f"),
        },
    )
