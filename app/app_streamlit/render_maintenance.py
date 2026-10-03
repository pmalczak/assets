# -*- coding: utf-8 -*-
"""Zakładka Maintenance — audyt / prune zbędnych wyciągów i starego cache."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from app_proc.data_root import get_cash_pool_root, get_online_data_root
from app_proc.data_steps_root import get_data_steps_root
from maintenance.prune_contained_degiro import (
    audit_degiro_statements,
    get_degiro_dir,
)
from maintenance.prune_contained_statements import (
    ACTION_CONTAINED,
    ACTION_DELETED,
    ACTION_SKIPPED,
    StatementAudit,
    audit_cash_pool_statements,
    format_gaps,
    format_results,
)
from maintenance.prune_stale_data_steps import (
    ACTION_DELETED as CACHE_DELETED,
    ACTION_STALE,
    active_schema_products,
    format_stale_results,
    prune_stale_data_steps,
)


def render_maintenance() -> None:
    st.subheader("Maintenance")
    st.caption(
        "Audyt zbędnych plików (okres zawarty w innym), luk w pokryciu oraz "
        "nieaktywnych wersji cache DATA_STEP (`sN`). "
        "Domyślnie dry-run — zaznacz usuwanie, żeby kasować jak `--delete` w CLI."
    )
    delete = st.checkbox(
        "Usuń (jak `--delete`) — dotyczy przycisków poniżej",
        value=False,
        key="maintenance_prune_delete",
    )
    st.divider()
    _render_cash_pool_prune(delete=delete)
    st.divider()
    _render_degiro_prune(delete=delete)
    st.divider()
    _render_stale_cache_prune(delete=delete)


def _render_cash_pool_prune(*, delete: bool) -> None:
    st.markdown("#### `prune_contained_statements` (cash_pool)")
    try:
        root = get_cash_pool_root()
        st.caption(f"Katalog: `{root}`")
    except Exception as exc:
        st.error(f"Brak cash_pool: {exc}")
        return

    if st.button("Uruchom prune_contained_statements", key="maintenance_prune_statements"):
        try:
            with st.spinner("Audyt wyciągów cash_pool..."):
                audit = audit_cash_pool_statements(root, delete=delete)
            st.session_state["maintenance_statements_audit"] = {
                "root": str(root),
                "delete": delete,
                "audit": audit,
            }
        except Exception as exc:
            st.error("Nie udało się uruchomić prune_contained_statements.")
            st.exception(exc)
            return

    payload = st.session_state.get("maintenance_statements_audit")
    if payload is None:
        st.info("Kliknij przycisk, aby uruchomić audyt cash_pool.")
        return
    _render_audit(
        payload["audit"],
        report_root=Path(payload["root"]),
        deleted=bool(payload["delete"]),
    )


def _render_degiro_prune(*, delete: bool) -> None:
    st.markdown("#### `prune_contained_degiro` (p_degiro)")
    try:
        assets_root = get_online_data_root()
        degiro_dir = get_degiro_dir(assets_root)
        st.caption(f"Katalog: `{degiro_dir}`")
    except Exception as exc:
        st.error(f"Brak katalogu DEGIRO: {exc}")
        return

    if st.button("Uruchom prune_contained_degiro", key="maintenance_prune_degiro"):
        try:
            with st.spinner("Audyt eksportów DEGIRO..."):
                audit = audit_degiro_statements(assets_root, delete=delete)
            st.session_state["maintenance_degiro_audit"] = {
                "root": str(degiro_dir.parent),
                "delete": delete,
                "audit": audit,
            }
        except Exception as exc:
            st.error("Nie udało się uruchomić prune_contained_degiro.")
            st.exception(exc)
            return

    payload = st.session_state.get("maintenance_degiro_audit")
    if payload is None:
        st.info("Kliknij przycisk, aby uruchomić audyt DEGIRO.")
        return
    _render_audit(
        payload["audit"],
        report_root=Path(payload["root"]),
        deleted=bool(payload["delete"]),
    )


def _render_audit(
    audit: StatementAudit,
    *,
    report_root: Path,
    deleted: bool,
) -> None:
    contained_n = sum(
        1 for r in audit.contained if r.action in {ACTION_CONTAINED, ACTION_DELETED}
    )
    skipped_n = sum(1 for r in audit.contained if r.action == ACTION_SKIPPED)
    mode = "usunięte" if deleted else "do usunięcia (dry-run)"

    c1, c2, c3 = st.columns(3)
    c1.metric(mode.capitalize(), contained_n)
    c2.metric("Pominięte", skipped_n)
    c3.metric("Luki", len(audit.gaps))

    if audit.contained:
        st.markdown("**Pliki zawarte w innych**")
        st.code(format_results(audit.contained, report_root) or "(brak)", language=None)
    else:
        st.success("Brak plików zawartych w innych.")

    if audit.gaps:
        st.markdown("**Luki w pokryciu**")
        st.code(format_gaps(audit.gaps), language=None)
    else:
        st.success("Brak luk w pokryciu okresów.")


def _render_stale_cache_prune(*, delete: bool) -> None:
    st.markdown(
        "#### `prune_stale_data_steps` (stare `sN` + przestarzałe produkty, np. `10 roi`)"
    )
    try:
        root = get_data_steps_root()
        st.caption(f"Katalog: `{root}`")
    except Exception as exc:
        st.error(f"Brak data_steps: {exc}")
        return

    active = active_schema_products()
    if active:
        st.caption(
            "Aktywne schematy: "
            + ", ".join(f"`{product}` → s{schema}" for product, schema in sorted(active.items()))
        )

    if st.button("Uruchom prune_stale_data_steps", key="maintenance_prune_stale_cache"):
        try:
            with st.spinner("Skanowanie nieaktywnych wersji cache..."):
                results = prune_stale_data_steps(root, delete=delete)
            st.session_state["maintenance_stale_cache"] = {
                "root": str(root),
                "delete": delete,
                "results": results,
            }
        except Exception as exc:
            st.error("Nie udało się uruchomić prune_stale_data_steps.")
            st.exception(exc)
            return

    payload = st.session_state.get("maintenance_stale_cache")
    if payload is None:
        st.info("Kliknij przycisk, aby znaleźć stare katalogi `sN` (np. s3 przy aktywnym s5).")
        return

    results = payload["results"]
    deleted = bool(payload["delete"])
    mode = "usunięte" if deleted else "do usunięcia (dry-run)"
    stale_n = sum(1 for r in results if r.action in {ACTION_STALE, CACHE_DELETED})
    c1, c2 = st.columns(2)
    c1.metric(mode.capitalize(), stale_n)
    c2.metric("Produkty", len({r.product for r in results}) if results else 0)

    if results:
        st.code(
            format_stale_results(results, Path(payload["root"])) or "(brak)",
            language=None,
        )
    else:
        st.success("Brak nieaktywnych wersji cache `sN`.")
