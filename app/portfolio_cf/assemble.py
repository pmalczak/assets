# -*- coding: utf-8 -*-
"""Składa kanoniczny ledger CF ze wszystkich adapterów venue."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from portfolio_cf.adapters.base import empty_ledger
from portfolio_cf.adapters.bonds import adapt_bonds_ledger
from portfolio_cf.adapters.catalog import adapt_catalog_ledger
from portfolio_cf.adapters.degiro import adapt_degiro_ledger
from portfolio_cf.adapters.deposits import adapt_deposits_ledger
from portfolio_cf.adapters.robo import adapt_robo_ledger
from portfolio_cf.adapters.xtb import adapt_xtb_ledger
from portfolio_cf.coverage import CoverageStatus, InstrumentCoverage
from portfolio_cf.data_model import InstrumentCashFlow
from portfolio_cf.instrument_portfolio import is_xirr_excluded_instrument
from portfolios.assignment import PORTFOLIO_DLUGOTERMINOWY_ASSET_IDS


@dataclass
class AssemblyResult:
    ledger: pd.DataFrame
    coverage: list[InstrumentCoverage]
    warnings: list[str] = field(default_factory=list)
    is_sold_by_instrument: dict[str, bool] = field(default_factory=dict)

    def coverage_frame(self) -> pd.DataFrame:
        if not self.coverage:
            return pd.DataFrame(
                columns=["instrument_id", "status", "reason", "venue", "is_sold"]
            )
        rows = []
        for item in self.coverage:
            row = item.to_row()
            row["is_sold"] = bool(self.is_sold_by_instrument.get(item.instrument_id, False))
            rows.append(row)
        return pd.DataFrame(rows)

    def uncovered(self) -> list[InstrumentCoverage]:
        return [item for item in self.coverage if item.status == CoverageStatus.UNCOVERED]


def build_instrument_ledger(
    valuation_date: date,
    *,
    fx_rates: pd.DataFrame | None = None,
    snapshot: pd.DataFrame | None = None,
) -> AssemblyResult:
    """Zbiera CF wszystkich venue; oznacza UNCOVERED z snapshota bez CF."""
    from portfolio_cf.sold_status import build_instrument_sold_map

    frames: list[pd.DataFrame] = []
    coverage: list[InstrumentCoverage] = []
    warnings: list[str] = []

    adapters = (
        adapt_catalog_ledger,
        adapt_robo_ledger,
        adapt_degiro_ledger,
        adapt_xtb_ledger,
        adapt_bonds_ledger,
        adapt_deposits_ledger,
    )
    for adapter in adapters:
        try:
            ledger, cov, warn = adapter(valuation_date, fx_rates=fx_rates)
        except Exception as exc:
            warnings.append(f"{adapter.__name__}: {exc}")
            continue
        coverage.extend(cov)
        warnings.extend(warn)
        if ledger is not None and not ledger.empty:
            frames.append(ledger)

    ledger = pd.concat(frames, ignore_index=True) if frames else empty_ledger()
    if not ledger.empty:
        ledger[InstrumentCashFlow.DATE] = (
            pd.to_datetime(ledger[InstrumentCashFlow.DATE], errors="coerce")
            .dt.strftime("%Y-%m-%d")
        )
        ledger = ledger.dropna(subset=[InstrumentCashFlow.DATE]).reset_index(drop=True)
        InstrumentCashFlow.check_structure(ledger)

    coverage.extend(_uncovered_from_snapshot(snapshot, coverage))
    coverage.extend(_uncovered_long_term(coverage))
    coverage = _dedupe_coverage(coverage)

    try:
        sold_map = build_instrument_sold_map(valuation_date)
    except Exception as exc:
        warnings.append(f"build_instrument_sold_map: {exc}")
        sold_map = {}

    return AssemblyResult(
        ledger=ledger,
        coverage=coverage,
        warnings=warnings,
        is_sold_by_instrument=sold_map,
    )


def _covered_ids(coverage: list[InstrumentCoverage]) -> set[str]:
    return {
        item.instrument_id
        for item in coverage
        if item.status in {CoverageStatus.COVERED, CoverageStatus.MANUAL, CoverageStatus.EXCLUDED}
    }


def _uncovered_from_snapshot(
    snapshot: pd.DataFrame | None,
    coverage: list[InstrumentCoverage],
) -> list[InstrumentCoverage]:
    if snapshot is None or snapshot.empty:
        return []
    from importers.assets.data_model import AssetsDef

    known = _covered_ids(coverage)
    out: list[InstrumentCoverage] = []
    id_col = AssetsDef.ID if AssetsDef.ID in snapshot.columns else None
    type_col = AssetsDef.TYPE if AssetsDef.TYPE in snapshot.columns else None
    if id_col is None:
        return []
    for _, row in snapshot.iterrows():
        asset_id = str(row[id_col]).strip()
        typ = str(row[type_col]).strip() if type_col else ""
        if not asset_id or asset_id in known:
            continue
        if is_xirr_excluded_instrument(asset_id, typ=typ):
            out.append(
                InstrumentCoverage(
                    instrument_id=asset_id,
                    status=CoverageStatus.EXCLUDED,
                    reason="cash_pool — poza XIRR portfela v1",
                    venue="snapshot",
                )
            )
            continue
        # Kontenery brokerów są COVERED przez instrumenty potomne — nie UNCOVERED.
        if asset_id in {"p_degiro", "p_xtb", "p_re_robo", "obligacjeskarbowe"}:
            out.append(
                InstrumentCoverage(
                    instrument_id=asset_id,
                    status=CoverageStatus.EXCLUDED,
                    reason="kontener brokera — CF na instrumentach potomnych",
                    venue="snapshot",
                )
            )
            continue
        if asset_id in PORTFOLIO_DLUGOTERMINOWY_ASSET_IDS:
            out.append(
                InstrumentCoverage(
                    instrument_id=asset_id,
                    status=CoverageStatus.UNCOVERED,
                    reason="brak CF venue (IKE / długoterminowy) — nie ma w roi_def",
                    venue="long_term",
                )
            )
            continue
        out.append(
            InstrumentCoverage(
                instrument_id=asset_id,
                status=CoverageStatus.UNCOVERED,
                reason="brak adaptera CF / legacy bez blottera",
                venue="snapshot",
            )
        )
    return out


def _uncovered_long_term(coverage: list[InstrumentCoverage]) -> list[InstrumentCoverage]:
    """IKE / rocky bez venue CF → UNCOVERED jeśli nie ma w ledgerze katalogu."""
    known = _covered_ids(coverage)
    out: list[InstrumentCoverage] = []
    for asset_id in sorted(PORTFOLIO_DLUGOTERMINOWY_ASSET_IDS):
        if asset_id in known:
            continue
        # rocky-iv często jest w katalogu — jeśli brak, uncovered
        out.append(
            InstrumentCoverage(
                instrument_id=asset_id,
                status=CoverageStatus.UNCOVERED,
                reason="brak CF venue (IKE / długoterminowy)",
                venue="long_term",
            )
        )
    return out


def _dedupe_coverage(coverage: list[InstrumentCoverage]) -> list[InstrumentCoverage]:
    """Pierwszy wpis wygrywa (COVERED z adaptera przed UNCOVERED ze snapshota)."""
    seen: set[str] = set()
    result: list[InstrumentCoverage] = []
    for item in coverage:
        if item.instrument_id in seen:
            continue
        seen.add(item.instrument_id)
        result.append(item)
    return result
