# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from app_streamlit.render_global_momentum import _load_benchmarks
from app_streamlit.column_layout import (
    amount_column_config,
    format_amount_columns,
    with_value_currency_pln_order,
)
from app_streamlit.safe_download import dataframe_for_streamlit, opt_in_download_button
from global_momentum.global_momentum_benchmarks import GM_U7_LABEL
from importers.assets.data_model import AssetsDef
from portfolio_cf.allocate import allocate_ledger_to_portfolio
from portfolio_cf.assemble import AssemblyResult, build_instrument_ledger
from portfolio_cf.coverage import CoverageStatus
from portfolio_cf.data_model import InstrumentCashFlow
from portfolio_cf.export_excel import portfolio_cf_excel_filename, portfolio_cf_to_excel_bytes
from portfolio_cf.instrument_portfolio import XIRR_EXCLUDED_PORTFOLIO, portfolio_for_instrument
from portfolio_cf.sold_status import (
    filter_coverage_by_sold,
    filter_ledger_by_sold,
    is_instrument_sold,
)
from portfolio_cf.xirr import compute_named_portfolio_xirr
from app_proc.ui_prefs import current_sold_filter
from portfolios.assignment import (
    KNOWN_PORTFOLIOS,
    PORTFOLIO_CASH_POOL,
    PORTFOLIO_GM,
    PORTFOLIO_PLYNNY,
    assets_in_portfolio,
    load_portfolio_nav_history,
    nav_pln_for_portfolio,
)
from portfolios.composition import (
    compose_gm_instrument_composition,
    load_gm_position_lines,
)
from portfolios.nav_path import nav_path_metrics, rebased_overlap

_PORTFOLIO_NAV_SCHEMA = 2
_GM_POSITIONS_SCHEMA = 1
_LEDGER_SCHEMA = 4
_PORTFOLIOS_SELECTED_KEY = "portfolios_selected_v2"
_LEGACY_PORTFOLIOS_SELECTED_KEYS = ("portfolios_selected",)
_COMPOSITION_COLUMNS = (
    AssetsDef.ID,
    AssetsDef.DESCR,
    AssetsDef.TYPE,
    AssetsDef.VALUE,
    AssetsDef.CURRENCY,
    AssetsDef.VALUE_PLN,
    AssetsDef.EVALUATION_DATE,
    AssetsDef.VALUE_DATE,
    AssetsDef.DAYS_AFTER_VALUATION,
)


@st.cache_data(show_spinner=False)
def _load_portfolio_nav(portfolio_name: str, _schema: int = _PORTFOLIO_NAV_SCHEMA) -> pd.Series:
    return load_portfolio_nav_history(portfolio_name)


@st.cache_data(show_spinner=False)
def _load_gm_positions(
    valuation_date: date,
    _schema: int = _GM_POSITIONS_SCHEMA,
) -> tuple[list, list[str]]:
    return load_gm_position_lines(valuation_date)


def _purge_stale_portfolio_selection() -> None:
    """Po zmianie etykiet portfeli stary wybór w session_state wywala pills."""
    for key in _LEGACY_PORTFOLIOS_SELECTED_KEYS:
        st.session_state.pop(key, None)
    current = st.session_state.get(_PORTFOLIOS_SELECTED_KEY)
    if current is not None and current not in KNOWN_PORTFOLIOS:
        st.session_state.pop(_PORTFOLIOS_SELECTED_KEY, None)


def render_portfolios() -> None:
    from app_streamlit.build_data import build_data

    data = build_data()
    latest_snapshot = data["latest_snapshot"]
    latest_snapshot_date = data["latest_snapshot_date"]
    if not isinstance(latest_snapshot, pd.DataFrame):
        latest_snapshot = pd.DataFrame()

    st.subheader("Portfele")
    st.caption(
        "NAV i skład ze snapshotów. XIRR portfela (nowe, dual-run) = concat CF instrumentów "
        "w PLN (NBP z dnia transakcji) + terminal NAV — równolegle do legacy ROI w zakładce ROI. "
        f"Porównanie do backtestu U7 tylko dla {PORTFOLIO_GM}."
    )

    if st.button("Odśwież NAV", key="portfolios_refresh"):
        _load_portfolio_nav.clear()
        _load_gm_positions.clear()
        _load_benchmarks.clear()
        _load_instrument_ledger_cached.clear()
        st.rerun()

    _purge_stale_portfolio_selection()
    selected = st.pills(
        "Portfel",
        options=list(KNOWN_PORTFOLIOS),
        default=PORTFOLIO_GM,
        required=True,
        key=_PORTFOLIOS_SELECTED_KEY,
        width="stretch",
    )

    if latest_snapshot.empty or latest_snapshot_date is None:
        st.warning("Brak snapshotu portfela — wygeneruj snapshot w Wartość aktywów.")
        return

    st.markdown(f"**Snapshot:** {latest_snapshot_date.isoformat()}")

    assembly = _render_portfolio_xirr(selected, latest_snapshot, latest_snapshot_date)

    if selected == PORTFOLIO_GM:
        _render_gm_composition(latest_snapshot, latest_snapshot_date)
    else:
        _render_generic_composition(latest_snapshot, selected)

    _render_cf_browser(selected, assembly, latest_snapshot_date)
    _render_nav_path(selected)


@st.cache_data(show_spinner=False)
def _load_instrument_ledger_cached(
    valuation_date: date,
    _schema: int = _LEDGER_SCHEMA,
) -> tuple[pd.DataFrame, pd.DataFrame, tuple[str, ...], dict[str, bool]]:
    from app_proc.snapshots import list_snapshot_files, load_snapshot, snapshots_directory

    snapshot = pd.DataFrame()
    for snap_date, path in list_snapshot_files(snapshots_directory()):
        if snap_date == valuation_date:
            snapshot = load_snapshot(path)
            break
    assembly = build_instrument_ledger(valuation_date, snapshot=snapshot)
    return (
        assembly.ledger,
        assembly.coverage_frame(),
        tuple(assembly.warnings),
        dict(assembly.is_sold_by_instrument),
    )


def _load_instrument_ledger(valuation_date: date) -> AssemblyResult:
    from portfolio_cf.coverage import InstrumentCoverage

    ledger, coverage_df, warnings, sold_map = _load_instrument_ledger_cached(valuation_date)
    coverage: list = []
    if coverage_df is not None and not coverage_df.empty:
        for _, row in coverage_df.iterrows():
            coverage.append(
                InstrumentCoverage(
                    instrument_id=str(row["instrument_id"]),
                    status=CoverageStatus(str(row["status"])),
                    reason=str(row.get("reason") or ""),
                    venue=str(row.get("venue") or ""),
                )
            )
    return AssemblyResult(
        ledger=ledger,
        coverage=coverage,
        warnings=list(warnings),
        is_sold_by_instrument=dict(sold_map or {}),
    )


def _render_portfolio_xirr(
    portfolio_name: str,
    snapshot: pd.DataFrame,
    valuation_date: date,
) -> AssemblyResult | None:
    if portfolio_name == PORTFOLIO_CASH_POOL or portfolio_name == XIRR_EXCLUDED_PORTFOLIO:
        st.info("XIRR portfela: `0 CASH-POOL` poza zakresem v1 (źródło finansowania).")
        return None

    try:
        with st.spinner("Ledger CF + XIRR portfela..."):
            assembly = _load_instrument_ledger(valuation_date)
            result = compute_named_portfolio_xirr(
                portfolio_name,
                valuation_date,
                assembly=assembly,
                snapshot=snapshot,
                sold_filter=current_sold_filter(),
            )
    except Exception as exc:
        st.warning(f"Nie udało się policzyć XIRR portfela: {exc}")
        return None

    for msg in result.warnings:
        st.warning(msg)

    c1, c2, c3 = st.columns(3)
    xirr_label = "XIRR (PLN)"
    if result.incomplete:
        xirr_label = "XIRR (PLN, niekompletne CF)"
    c1.metric(
        xirr_label,
        f"{result.xirr:.2%}" if result.xirr is not None else "—",
    )
    c2.metric("Terminal NAV", f"{result.terminal_pln:,.0f} PLN".replace(",", " "))
    c3.metric("ROI nominalny", f"{result.roi_nominal_pln:,.0f} PLN".replace(",", " "))
    st.caption(
        f"XIRR = jeden compute_xirr na CF instrumentów (amount_pln) + terminal. "
        f"Filtr pozycji (sidebar): **{current_sold_filter()}**. "
        "Dual-run względem zakładki ROI."
    )
    if result.uncovered:
        lines = [
            f"`{item.instrument_id}` — {item.reason or item.status.value}"
            for item in result.uncovered
        ]
        st.info(
            "Instrumenty portfela **bez CF** (UNCOVERED; w XIRR brak ich przepływów, "
            "NAV terminala i tak z całego portfela):\n\n- " + "\n- ".join(lines)
        )
    return assembly


def _render_cf_browser(
    portfolio_name: str,
    assembly: AssemblyResult | None,
    valuation_date: date,
) -> None:
    if assembly is None or portfolio_name == PORTFOLIO_CASH_POOL:
        return

    with st.expander("CF instrumentów (ledger)", expanded=False):
        mode = current_sold_filter()
        st.caption(f"Filtr pozycji (sidebar): **{mode}**")
        subset = allocate_ledger_to_portfolio(assembly.ledger, portfolio_name)
        subset = filter_ledger_by_sold(
            subset, assembly.is_sold_by_instrument, sold_filter=mode
        )
        coverage_visible = filter_coverage_by_sold(
            [
                item
                for item in assembly.coverage
                if portfolio_for_instrument(item.instrument_id) == portfolio_name
                and item.status != CoverageStatus.EXCLUDED
            ],
            assembly.is_sold_by_instrument,
            sold_filter=mode,
        )
        uncovered = [
            item for item in coverage_visible if item.status == CoverageStatus.UNCOVERED
        ]
        covered_ids = (
            sorted(subset[InstrumentCashFlow.INSTRUMENT_ID].astype(str).unique())
            if not subset.empty
            else []
        )
        uncovered_ids = [item.instrument_id for item in uncovered]
        instruments = sorted(set(covered_ids) | set(uncovered_ids))

        opt_in_download_button(
            prepare_label="Przygotuj pobieranie CF portfela (Excel)",
            prepare_key=f"prepare_portfolio_cf_xlsx_{portfolio_name}",
            button_label="Pobierz CF portfela (Excel)",
            data_factory=lambda: portfolio_cf_to_excel_bytes(
                assembly,
                portfolio_name,
                valuation_date,
                sold_filter=mode,
            ),
            file_name=portfolio_cf_excel_filename(portfolio_name, valuation_date),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            download_key=f"portfolio_cf_xlsx_{portfolio_name}",
            disabled=subset.empty and not uncovered,
            help_prepare=(
                "Excel w perspektywie portfela (po filtrze pozycji): arkusz cf, coverage, meta. "
                "Na Python 3.14 włącz tylko na czas pobrania."
            ),
        )

        coverage_rows = []
        for item in coverage_visible:
            coverage_rows.append(
                {
                    "instrument_id": item.instrument_id,
                    "status": item.status.value,
                    "is_sold": is_instrument_sold(
                        item.instrument_id, assembly.is_sold_by_instrument
                    ),
                    "reason": item.reason,
                    "venue": item.venue,
                }
            )
        if coverage_rows:
            st.caption("Pokrycie CF instrumentów tego portfela")
            st.dataframe(
                dataframe_for_streamlit(pd.DataFrame(coverage_rows).sort_values("instrument_id")),
                width="stretch",
                hide_index=True,
            )
        elif not instruments:
            st.info(f"Brak instrumentów dla filtra: {mode}.")
            return

        if not instruments:
            st.info(f"Brak instrumentów z coverage/ledger dla filtra: {mode}.")
            return

        chosen = st.selectbox(
            "Instrument",
            options=["(wszystkie z CF)"] + instruments,
            key=f"portfolio_cf_instrument_{portfolio_name}",
        )
        if chosen != "(wszystkie z CF)" and chosen in uncovered_ids and chosen not in covered_ids:
            item = next(u for u in uncovered if u.instrument_id == chosen)
            st.warning(
                f"`{chosen}` jest UNCOVERED — brak przepływów w ledgerze "
                f"({item.reason or 'brak adaptera CF'})."
            )
            return

        view = subset
        if chosen != "(wszystkie z CF)":
            view = subset.loc[
                subset[InstrumentCashFlow.INSTRUMENT_ID].astype(str) == chosen
            ]
        if view.empty:
            st.info("Brak wierszy CF dla wybranego filtra.")
            return
        cols = [
            InstrumentCashFlow.DATE,
            InstrumentCashFlow.INSTRUMENT_ID,
            InstrumentCashFlow.CATEGORY,
            InstrumentCashFlow.AMOUNT,
            InstrumentCashFlow.CURRENCY,
            InstrumentCashFlow.AMOUNT_PLN,
            InstrumentCashFlow.FX_RATE,
            InstrumentCashFlow.FX_DATE,
            InstrumentCashFlow.DESCRIPTION,
        ]
        display = view[[c for c in cols if c in view.columns]].copy()
        display[InstrumentCashFlow.DATE] = pd.to_datetime(
            display[InstrumentCashFlow.DATE], errors="coerce"
        )
        display = display.sort_values(InstrumentCashFlow.DATE, ascending=False)
        display[InstrumentCashFlow.DATE] = display[InstrumentCashFlow.DATE].dt.strftime(
            "%Y-%m-%d"
        )
        st.dataframe(
            dataframe_for_streamlit(display),
            width="stretch",
            hide_index=True,
        )


def _render_generic_composition(snapshot: pd.DataFrame, portfolio_name: str) -> None:
    total_nav = nav_pln_for_portfolio(snapshot, portfolio_name)
    st.metric(f"NAV {portfolio_name}", f"{total_nav:,.0f} PLN".replace(",", " "))
    table = _composition_table(snapshot, portfolio_name)
    if table.empty:
        st.info(f"Brak wierszy w tym snapshocie dla {portfolio_name}.")
        return
    display = dataframe_for_streamlit(table)
    st.dataframe(
        display,
        width="stretch",
        hide_index=True,
        column_config=amount_column_config(display),
    )


def _composition_table(snapshot: pd.DataFrame, portfolio_name: str) -> pd.DataFrame:
    part = assets_in_portfolio(snapshot, portfolio_name)
    if part is None or part.empty:
        return pd.DataFrame()
    cols = [column for column in _COMPOSITION_COLUMNS if column in part.columns]
    if not cols:
        return pd.DataFrame()
    out = with_value_currency_pln_order(part[cols].copy())
    if AssetsDef.VALUE_PLN in out.columns:
        out[AssetsDef.VALUE_PLN] = pd.to_numeric(out[AssetsDef.VALUE_PLN], errors="coerce").fillna(0)
        out = out.sort_values(AssetsDef.VALUE_PLN, ascending=False)
    return out


def _render_gm_composition(
    latest_snapshot: pd.DataFrame,
    latest_snapshot_date: date,
) -> None:
    st.caption(
        f"Alokacja per instrument (DEGIRO + XTB). Cel U7 ≈ 1/3 NAV na aktywo. "
        f"Data snapshotu ≠ data sygnału U7. Portfel {PORTFOLIO_GM} bez złota "
        f"(złoto w {PORTFOLIO_PLYNNY})."
    )

    lines: list = []
    position_warnings: list[str] = []
    try:
        with st.spinner("Ładowanie pozycji instrumentów..."):
            lines, position_warnings = _load_gm_positions(latest_snapshot_date)
    except Exception as exc:
        position_warnings = [f"Nie udało się wczytać pozycji: {exc}"]

    for msg in position_warnings:
        st.warning(msg)

    total_nav = nav_pln_for_portfolio(latest_snapshot, PORTFOLIO_GM)
    table = compose_gm_instrument_composition(latest_snapshot, lines)
    position_nav = 0.0
    if not table.empty and "kind" in table.columns:
        position_nav = float(
            table.loc[table["kind"] == "position", AssetsDef.VALUE_PLN].sum()
        )

    c1, c2 = st.columns(2)
    c1.metric(f"NAV {PORTFOLIO_GM}", f"{total_nav:,.0f} PLN".replace(",", " "))
    c2.metric("Pozycje (bez gotówki)", f"{position_nav:,.0f} PLN".replace(",", " "))

    if table.empty:
        st.info(
            "Brak pozycji instrumentów dla tego snapshota — "
            "sprawdź wyciągi DEGIRO/XTB albo wygeneruj ponownie snapshot."
        )
        return

    display = format_amount_columns(
        with_value_currency_pln_order(table.drop(columns=["kind"], errors="ignore"))
    )
    st.dataframe(
        display,
        width="stretch",
        hide_index=True,
        column_config=amount_column_config(
            display,
            {
                "Udział": st.column_config.NumberColumn(format="percent"),
            },
        ),
    )


def _render_nav_path(portfolio_name: str) -> None:
    compare_u7 = portfolio_name == PORTFOLIO_GM
    if compare_u7:
        st.markdown("**Ścieżka NAV vs backtest U7**")
        st.caption(
            f"NAV portfela {PORTFOLIO_GM} ze snapshotów (PLN) zawiera dopłaty — to nie XIRR i nie czysty TWR bez CF. "
            "Porównanie: obie serie = 100 na wspólnym starcie. Backtest U7 to stały kapitał (EUR)."
        )
    else:
        st.markdown("**Ścieżka NAV**")
        st.caption(
            "NAV ze snapshotów zawiera dopłaty — to nie XIRR i nie czysty TWR."
        )

    try:
        with st.spinner(f"Ładowanie historii NAV {portfolio_name}..."):
            portfolio_nav = _load_portfolio_nav(portfolio_name)
    except Exception as exc:
        st.error(f"Nie udało się złożyć ścieżki NAV portfela {portfolio_name}.")
        st.exception(exc)
        return

    portfolio_nav = portfolio_nav.rename(f"Portfel {portfolio_name} NAV")
    metrics = nav_path_metrics(portfolio_nav)
    if metrics:
        m1, m2, m3 = st.columns(3)
        m1.metric(
            "CAGR NAV",
            f"{metrics['CAGR']:.2%}" if "CAGR" in metrics else "—",
        )
        m2.metric("Max DD NAV", f"{metrics['Max Drawdown']:.2%}")
        m3.metric("Zmiana NAV", f"{metrics['Total Return']:.2%}")
    elif portfolio_nav.empty:
        st.info(f"Brak historii snapshotów dla portfela {portfolio_name}.")
        return
    else:
        st.info("Za mało dodatnich punktów NAV, żeby policzyć CAGR / DD.")

    if not compare_u7:
        if not portfolio_nav.empty:
            st.line_chart(portfolio_nav, width="stretch")
        return

    try:
        with st.spinner("Ładowanie backtestu U7 do porównania..."):
            benchmarks = _load_benchmarks()
    except Exception as exc:
        st.warning("Backtest U7 niedostępny — pokazuję samą ścieżkę NAV.")
        st.exception(exc)
        if not portfolio_nav.empty:
            st.line_chart(portfolio_nav, width="stretch")
        return

    u7_equity = pd.Series(dtype=float)
    equity = benchmarks.get("equity")
    if isinstance(equity, pd.DataFrame) and GM_U7_LABEL in equity.columns:
        u7_equity = equity[GM_U7_LABEL].copy()
        u7_equity.name = GM_U7_LABEL
    comparison = rebased_overlap(portfolio_nav, u7_equity)
    if comparison.empty:
        st.info(f"Brak wspólnego okresu NAV portfela {PORTFOLIO_GM} i backtestu U7.")
        st.line_chart(portfolio_nav, width="stretch")
        return
    st.line_chart(comparison, width="stretch")
