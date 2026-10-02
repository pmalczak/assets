# -*- coding: utf-8 -*-
"""XIRR nazwanego portfela: lokalny (FX_T) + spot PLN + atrybucja FX.

Semantyka metryk: ``Cursor_rules.md`` → *XIRR portfela a FX*.
``xirr`` = lokalny (kanoniczny); ``xirr_pln`` = spot; Razem UI = ``build_portfolio_razem_row``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from app_proc.ui_prefs import SOLD_FILTER_SOLD
from portfolio_cf.allocate import allocate_ledger_to_portfolio
from portfolio_cf.assemble import AssemblyResult, build_instrument_ledger
from portfolio_cf.coverage import CoverageStatus, InstrumentCoverage
from portfolio_cf.data_model import InstrumentCashFlow
from portfolio_cf.fx_attribution import (
    local_pln_series,
    roi_fx_components,
    spot_pln_series,
)
from portfolio_cf.instrument_portfolio import portfolio_for_instrument
from portfolio_cf.sold_status import (
    filter_coverage_by_sold,
    filter_ledger_by_sold,
    sold_filter_label,
)
from portfolios.assignment import KNOWN_PORTFOLIOS, nav_pln_for_portfolio
from portfolios.composition import (
    broker_cash_pln_for_portfolio,
    load_broker_holdings_for_portfolios,
    split_broker_nav_for_instrument_overrides,
)
from roi.xirr import compute_xirr

RAP_TOTAL = "Z RAZEM"


def _ledger_excluding_broker_cash(ledger: pd.DataFrame) -> pd.DataFrame:
    """Broker ``*:CASH`` nie wchodzi do CF/XIRR (gotówka robocza tylko w składzie/NAV)."""
    if ledger is None or ledger.empty:
        return ledger if ledger is not None else pd.DataFrame()
    ids = ledger[InstrumentCashFlow.INSTRUMENT_ID].astype(str)
    return ledger.loc[~ids.str.endswith(":CASH")].copy()


def _terminal_positions_pln(
    snapshot: pd.DataFrame,
    portfolio_name: str,
    valuation_date: date,
    *,
    holdings_by_id: dict | None = None,
    warnings: list[str] | None = None,
) -> float:
    """NAV portfela ze snapshota minus gotówka robocza brokerów (XIRR = pozycje)."""
    split = split_broker_nav_for_instrument_overrides(snapshot, valuation_date)
    terminal = float(nav_pln_for_portfolio(split, portfolio_name))
    if holdings_by_id is None:
        holdings_by_id, hold_warnings = load_broker_holdings_for_portfolios(valuation_date)
        if warnings is not None:
            warnings.extend(hold_warnings)
    cash = broker_cash_pln_for_portfolio(snapshot, portfolio_name, holdings_by_id)
    return terminal - float(cash)


@dataclass
class PortfolioXirrResult:
    portfolio: str
    valuation_date: date
    xirr: float | None  # lokalny (constant FX_T) — kanoniczna rentowność
    xirr_pln: float | None  # spot (FX_t)
    terminal_pln: float
    cf_pln_sum: float
    roi_nominal_pln: float
    roi_local_pln: float
    roi_fx_pln: float
    fx_share: float | None
    n_cashflows: int
    incomplete: bool
    warnings: list[str] = field(default_factory=list)
    uncovered: list[InstrumentCoverage] = field(default_factory=list)


def compute_named_portfolio_xirr(
    portfolio_name: str,
    valuation_date: date,
    *,
    assembly: AssemblyResult | None = None,
    snapshot: pd.DataFrame | None = None,
    terminal_pln: float | None = None,
    fx_rates: pd.DataFrame | None = None,
    sold_filter: str | None = None,
    holdings_by_id: dict | None = None,
) -> PortfolioXirrResult:
    """XIRR lokalny + spot oraz ROI_PLN / ROI_local / ROI_FX na CF portfela.

    Uwzględnia globalny filtr sprzedane/niesprzedane (jak ROI Razem).
    UNCOVERED (po filtrze) z niezerowym NAV → warning + incomplete=True.
    Terminal = NAV pozycji (bez gotówki roboczej brokerów), o ile nie podano ``terminal_pln``.
    """
    if assembly is None:
        assembly = build_instrument_ledger(
            valuation_date, fx_rates=fx_rates, snapshot=snapshot
        )

    mode = sold_filter if sold_filter is not None else sold_filter_label()
    subset = allocate_ledger_to_portfolio(assembly.ledger, portfolio_name)
    subset = filter_ledger_by_sold(
        subset, assembly.is_sold_by_instrument, sold_filter=mode
    )
    subset = _ledger_excluding_broker_cash(subset)
    warnings = list(assembly.warnings)
    uncovered_in_portfolio = filter_coverage_by_sold(
        [
            item
            for item in assembly.coverage
            if item.status == CoverageStatus.UNCOVERED
            and portfolio_for_instrument(item.instrument_id) == portfolio_name
        ],
        assembly.is_sold_by_instrument,
        sold_filter=mode,
    )

    if terminal_pln is None:
        if mode == SOLD_FILTER_SOLD:
            terminal_pln = 0.0
        elif snapshot is not None and not snapshot.empty:
            terminal_pln = _terminal_positions_pln(
                snapshot,
                portfolio_name,
                valuation_date,
                holdings_by_id=holdings_by_id,
                warnings=warnings,
            )
        else:
            terminal_pln = 0.0

    incomplete = False
    if uncovered_in_portfolio and abs(terminal_pln) > 1e-6:
        incomplete = True
        ids = ", ".join(item.instrument_id for item in uncovered_in_portfolio[:8])
        more = "" if len(uncovered_in_portfolio) <= 8 else "…"
        warnings.append(
            f"XIRR {portfolio_name}: niekompletne CF (UNCOVERED z NAV): {ids}{more}"
        )

    return _result_from_ledger(
        portfolio_name=portfolio_name,
        valuation_date=valuation_date,
        ledger=subset,
        terminal_pln=float(terminal_pln),
        fx_rates=fx_rates,
        incomplete=incomplete,
        warnings=warnings,
        uncovered=uncovered_in_portfolio,
    )


def compute_total_portfolio_xirr(
    valuation_date: date,
    *,
    assembly: AssemblyResult | None = None,
    snapshot: pd.DataFrame | None = None,
    fx_rates: pd.DataFrame | None = None,
    sold_filter: str | None = None,
    holdings_by_id: dict | None = None,
) -> PortfolioXirrResult:
    """XIRR / ROI FX dla Z RAZEM (wszystkie portfele poza 0 CASH-POOL)."""
    from portfolio_cf.instrument_portfolio import XIRR_EXCLUDED_PORTFOLIO

    if assembly is None:
        assembly = build_instrument_ledger(
            valuation_date, fx_rates=fx_rates, snapshot=snapshot
        )

    mode = sold_filter if sold_filter is not None else sold_filter_label()
    frames: list[pd.DataFrame] = []
    terminal = 0.0
    warnings = list(assembly.warnings)
    uncovered: list[InstrumentCoverage] = []
    resolved_holdings = holdings_by_id
    if (
        resolved_holdings is None
        and mode != SOLD_FILTER_SOLD
        and snapshot is not None
        and not snapshot.empty
    ):
        resolved_holdings, hold_warnings = load_broker_holdings_for_portfolios(
            valuation_date
        )
        warnings.extend(hold_warnings)

    for name in KNOWN_PORTFOLIOS:
        if name == XIRR_EXCLUDED_PORTFOLIO:
            continue
        part = allocate_ledger_to_portfolio(assembly.ledger, name)
        part = filter_ledger_by_sold(
            part, assembly.is_sold_by_instrument, sold_filter=mode
        )
        part = _ledger_excluding_broker_cash(part)
        if part is not None and not part.empty:
            frames.append(part)
        if mode == SOLD_FILTER_SOLD:
            part_terminal = 0.0
        elif snapshot is not None and not snapshot.empty:
            part_terminal = _terminal_positions_pln(
                snapshot,
                name,
                valuation_date,
                holdings_by_id=resolved_holdings if resolved_holdings is not None else {},
                warnings=warnings,
            )
        else:
            part_terminal = 0.0
        terminal += part_terminal
        uncovered.extend(
            filter_coverage_by_sold(
                [
                    item
                    for item in assembly.coverage
                    if item.status == CoverageStatus.UNCOVERED
                    and portfolio_for_instrument(item.instrument_id) == name
                ],
                assembly.is_sold_by_instrument,
                sold_filter=mode,
            )
        )

    if frames:
        ledger = pd.concat(frames, ignore_index=True)
    else:
        ledger = pd.DataFrame(columns=list(InstrumentCashFlow.COLUMN_ORDER))

    incomplete = False
    if uncovered and abs(terminal) > 1e-6:
        incomplete = True
        warnings.append(
            f"XIRR {RAP_TOTAL}: niekompletne CF (UNCOVERED z NAV)"
        )

    return _result_from_ledger(
        portfolio_name=RAP_TOTAL,
        valuation_date=valuation_date,
        ledger=ledger,
        terminal_pln=float(terminal),
        fx_rates=fx_rates,
        incomplete=incomplete,
        warnings=warnings,
        uncovered=uncovered,
    )


def compute_named_portfolio_xirr_map(
    valuation_date: date,
    *,
    assembly: AssemblyResult | None = None,
    snapshot: pd.DataFrame | None = None,
    sold_filter: str | None = None,
    fx_rates: pd.DataFrame | None = None,
    holdings_by_id: dict | None = None,
) -> dict[str, float | None]:
    """XIRR lokalny per portfel (+ Z RAZEM). CASH-POOL → None."""
    metrics = compute_named_portfolio_metrics_map(
        valuation_date,
        assembly=assembly,
        snapshot=snapshot,
        sold_filter=sold_filter,
        fx_rates=fx_rates,
        holdings_by_id=holdings_by_id,
    )
    return {name: row.xirr for name, row in metrics.items()}


def compute_named_portfolio_metrics_map(
    valuation_date: date,
    *,
    assembly: AssemblyResult | None = None,
    snapshot: pd.DataFrame | None = None,
    sold_filter: str | None = None,
    fx_rates: pd.DataFrame | None = None,
    holdings_by_id: dict | None = None,
) -> dict[str, PortfolioXirrResult]:
    """Pełne metryki XIRR/FX per nazwany portfel + Z RAZEM."""
    from portfolio_cf.instrument_portfolio import XIRR_EXCLUDED_PORTFOLIO

    if assembly is None:
        assembly = build_instrument_ledger(
            valuation_date, fx_rates=fx_rates, snapshot=snapshot
        )

    resolved_holdings = holdings_by_id
    if (
        resolved_holdings is None
        and snapshot is not None
        and not snapshot.empty
    ):
        resolved_holdings, _hold_warnings = load_broker_holdings_for_portfolios(
            valuation_date
        )

    out: dict[str, PortfolioXirrResult] = {}
    for name in KNOWN_PORTFOLIOS:
        if name == XIRR_EXCLUDED_PORTFOLIO:
            out[name] = _empty_excluded(name, valuation_date)
            continue
        try:
            out[name] = compute_named_portfolio_xirr(
                name,
                valuation_date,
                assembly=assembly,
                snapshot=snapshot,
                sold_filter=sold_filter,
                fx_rates=fx_rates,
                holdings_by_id=resolved_holdings,
            )
        except Exception:
            out[name] = _empty_excluded(name, valuation_date)
    try:
        out[RAP_TOTAL] = compute_total_portfolio_xirr(
            valuation_date,
            assembly=assembly,
            snapshot=snapshot,
            sold_filter=sold_filter,
            fx_rates=fx_rates,
            holdings_by_id=resolved_holdings,
        )
    except Exception:
        out[RAP_TOTAL] = _empty_excluded(RAP_TOTAL, valuation_date)
    return out


def _result_from_ledger(
    *,
    portfolio_name: str,
    valuation_date: date,
    ledger: pd.DataFrame,
    terminal_pln: float,
    fx_rates: pd.DataFrame | None,
    incomplete: bool,
    warnings: list[str],
    uncovered: list[InstrumentCoverage],
) -> PortfolioXirrResult:
    local_dates, local_amounts = local_pln_series(
        ledger, valuation_date, terminal_pln, fx_rates=fx_rates
    )
    spot_dates, spot_amounts = spot_pln_series(ledger, valuation_date, terminal_pln)
    xirr_local = compute_xirr(local_dates, local_amounts) if local_dates else None
    xirr_spot = compute_xirr(spot_dates, spot_amounts) if spot_dates else None
    components = roi_fx_components(
        ledger, terminal_pln, valuation_date, fx_rates=fx_rates
    )
    cf_sum = (
        float(ledger[InstrumentCashFlow.AMOUNT_PLN].sum())
        if ledger is not None and not ledger.empty
        else 0.0
    )
    return PortfolioXirrResult(
        portfolio=portfolio_name,
        valuation_date=valuation_date,
        xirr=xirr_local,
        xirr_pln=xirr_spot,
        terminal_pln=float(terminal_pln),
        cf_pln_sum=cf_sum,
        roi_nominal_pln=components.roi_pln,
        roi_local_pln=components.roi_local,
        roi_fx_pln=components.roi_fx,
        fx_share=components.fx_share,
        n_cashflows=len(local_dates),
        incomplete=incomplete,
        warnings=warnings,
        uncovered=uncovered,
    )


def build_portfolio_razem_row(
    summary: pd.DataFrame,
    result: PortfolioXirrResult,
) -> pd.DataFrame:
    """Wiersz Razem portfela: suma CAPEX/… z wierszy + XIRR/ROI/terminal z ``result``.

    Jedyna ścieżka metryk portfela — nie liczyć drugiego XIRR z Σ terminali
    instrumentów (NAV portfela = MTM pozycji + gotówka; Σ wierszy tickerów bez CASH).
    """
    from importers.assets.data_model import AssetsDef
    from roi.aggregate_venue_roi import VENUE_TOTAL_ASSET_ID

    if summary is None or summary.empty:
        return pd.DataFrame()

    def _sum(col: str) -> float:
        if col not in summary.columns:
            return 0.0
        return float(pd.to_numeric(summary[col], errors="coerce").fillna(0).sum())

    eval_date: str | None = None
    if AssetsDef.EVALUATION_DATE in summary.columns:
        parsed = pd.to_datetime(summary[AssetsDef.EVALUATION_DATE], errors="coerce")
        valid = parsed.dropna()
        if not valid.empty:
            eval_date = valid.min().date().isoformat()

    row: dict[str, object] = {
        "asset_id": VENUE_TOTAL_ASSET_ID,
        "capex": round(_sum("capex")),
        "opex": round(_sum("opex")),
        "revenue": round(_sum("revenue")),
        "terminal_realized": round(_sum("terminal_realized")),
        "terminal_unrealized": round(result.terminal_pln),
        "roi_nominal": round(result.roi_nominal_pln),
        "roi_local": round(result.roi_local_pln),
        "roi_fx": round(result.roi_fx_pln),
        "fx_share": result.fx_share,
        "xirr": result.xirr,
        "xirr_pln": result.xirr_pln,
        "is_sold": bool(summary["is_sold"].all()) if "is_sold" in summary.columns else False,
        "warnings": "",
    }
    if eval_date is not None:
        row[AssetsDef.EVALUATION_DATE] = eval_date
    if "instrument" in summary.columns:
        row["instrument"] = VENUE_TOTAL_ASSET_ID
    return pd.DataFrame([row])


def _empty_excluded(portfolio_name: str, valuation_date: date) -> PortfolioXirrResult:
    return PortfolioXirrResult(
        portfolio=portfolio_name,
        valuation_date=valuation_date,
        xirr=None,
        xirr_pln=None,
        terminal_pln=0.0,
        cf_pln_sum=0.0,
        roi_nominal_pln=0.0,
        roi_local_pln=0.0,
        roi_fx_pln=0.0,
        fx_share=None,
        n_cashflows=0,
        incomplete=False,
    )
