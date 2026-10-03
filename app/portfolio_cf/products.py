# -*- coding: utf-8 -*-
"""Produkty DATA_STEP dla portfolio_cf (ledger / coverage / XIRR portfeli)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from app_proc.snapshots import snapshots_directory
from app_proc.ui_prefs import SOLD_FILTER_LABELS
from data_step.data_step import DATA_STEP
from data_step.data_step_frame import DataStepFrame
from portfolio_cf.assemble import AssemblyResult, build_instrument_ledger
from portfolio_cf.coverage import CoverageStatus, InstrumentCoverage
from portfolio_cf.data_model import InstrumentCashFlow
from app_proc.portfolio_cf_step import PORTFOLIO_CF_SCHEMA, portfolio_cf_prefix
from portfolio_cf.xirr import compute_named_portfolio_metrics_map

# Re-export — stała kanoniczna w ``app_proc.portfolio_cf_step``.
_PORTFOLIO_CF_SCHEMA = PORTFOLIO_CF_SCHEMA

_XIRR_COLUMNS = (
    "portfolio",
    "sold_filter",
    "xirr",
    "xirr_pln",
    "roi_pln",
    "roi_local",
    "roi_fx",
    "fx_share",
)


def ledger_resource(valuation_date: date) -> str:
    return f"{portfolio_cf_prefix(valuation_date)}/_ledger.parquet"


def coverage_resource(valuation_date: date) -> str:
    return f"{portfolio_cf_prefix(valuation_date)}/_coverage.parquet"


def warnings_resource(valuation_date: date) -> str:
    return f"{portfolio_cf_prefix(valuation_date)}/_warnings.parquet"


def xirr_resource(valuation_date: date) -> str:
    return f"{portfolio_cf_prefix(valuation_date)}/_xirr.parquet"


_ASSEMBLY_BUILD: dict[str, AssemblyResult] = {}


def snapshot_parquet_path(valuation_date: date) -> Path:
    return snapshots_directory() / f"{valuation_date:%Y-%m-%d}.parquet"


def load_assembly(valuation_date: date) -> AssemblyResult:
    """Ledger + coverage + sold_map + warnings z DATA_STEP (zależność: plik snapshota)."""
    ledger_df, coverage_df, warnings = _obtain_assembly_parts(valuation_date)
    assembly = _assembly_from_frames(ledger_df, coverage_df)
    assembly.warnings = list(warnings)
    return assembly


def load_portfolio_xirr_map(
    valuation_date: date,
    sold_filter: str,
) -> dict[str, float | None]:
    """XIRR lokalny per portfel dla wybranego filtra pozycji — z produktu DATA_STEP."""
    metrics = load_portfolio_metrics_map(valuation_date, sold_filter)
    return {name: row.get("xirr") for name, row in metrics.items()}


def load_portfolio_metrics_map(
    valuation_date: date,
    sold_filter: str,
) -> dict[str, dict[str, float | None]]:
    """XIRR lokalny / spot + ROI FX per portfel (w tym Z RAZEM)."""
    table = _obtain_xirr_table(valuation_date)
    if table is None or table.empty:
        return {}
    subset = table.loc[table["sold_filter"].astype(str) == str(sold_filter)]
    out: dict[str, dict[str, float | None]] = {}
    for _, row in subset.iterrows():
        portfolio = str(row["portfolio"])
        out[portfolio] = {
            "xirr": _nullable_float(row.get("xirr")),
            "xirr_pln": _nullable_float(row.get("xirr_pln")),
            "roi_pln": _nullable_float(row.get("roi_pln")),
            "roi_local": _nullable_float(row.get("roi_local")),
            "roi_fx": _nullable_float(row.get("roi_fx")),
            "fx_share": _nullable_float(row.get("fx_share")),
        }
    return out


def _nullable_float(raw: object) -> float | None:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def invalidate_portfolio_cf(valuation_date: date) -> None:
    """Usuwa produkty portfolio_cf na datę (kolejny load przebuduje)."""
    for resource in (
        ledger_resource(valuation_date),
        coverage_resource(valuation_date),
        warnings_resource(valuation_date),
        xirr_resource(valuation_date),
    ):
        try:
            DATA_STEP.invalidate(resource)
        except Exception:
            continue
    _ASSEMBLY_BUILD.pop(_stash_key(valuation_date), None)


def _obtain_assembly_parts(
    valuation_date: date,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    ledger_frame, coverage_frame, warnings_frame = _obtain_core_frames(valuation_date)
    _ASSEMBLY_BUILD.pop(_stash_key(valuation_date), None)
    warnings: list[str] = []
    warn_df = warnings_frame.data_frame()
    if warn_df is not None and not warn_df.empty and "message" in warn_df.columns:
        warnings = [str(m) for m in warn_df["message"].tolist() if str(m).strip()]
    return ledger_frame.data_frame(), coverage_frame.data_frame(), warnings


def _obtain_core_frames(
    valuation_date: date,
) -> tuple[DataStepFrame, DataStepFrame, DataStepFrame]:
    snap_path = snapshot_parquet_path(valuation_date)
    if snap_path.is_file():
        ledger_frame = DATA_STEP.obtain_dependent(
            ledger_resource(valuation_date),
            _collect_ledger,
            snap_path,
            valuation_date=valuation_date,
        )
        coverage_frame = DATA_STEP.obtain_dependent(
            coverage_resource(valuation_date),
            _collect_coverage,
            snap_path,
            valuation_date=valuation_date,
            ledger=ledger_frame,
        )
        warnings_frame = DATA_STEP.obtain_dependent(
            warnings_resource(valuation_date),
            _collect_warnings,
            snap_path,
            valuation_date=valuation_date,
            ledger=ledger_frame,
        )
    else:
        ledger_frame = DATA_STEP.obtain(
            ledger_resource(valuation_date),
            _collect_ledger,
            valuation_date=valuation_date,
        )
        coverage_frame = DATA_STEP.obtain(
            coverage_resource(valuation_date),
            _collect_coverage,
            valuation_date=valuation_date,
            ledger=ledger_frame,
        )
        warnings_frame = DATA_STEP.obtain(
            warnings_resource(valuation_date),
            _collect_warnings,
            valuation_date=valuation_date,
            ledger=ledger_frame,
        )
    return ledger_frame, coverage_frame, warnings_frame


def _obtain_xirr_table(valuation_date: date) -> pd.DataFrame:
    snap_path = snapshot_parquet_path(valuation_date)
    ledger_frame, coverage_frame, _warnings_frame = _obtain_core_frames(valuation_date)
    if snap_path.is_file():
        result = DATA_STEP.obtain_dependent(
            xirr_resource(valuation_date),
            _collect_xirr,
            snap_path,
            valuation_date=valuation_date,
            ledger=ledger_frame,
            coverage=coverage_frame,
        )
    else:
        result = DATA_STEP.obtain(
            xirr_resource(valuation_date),
            _collect_xirr,
            valuation_date=valuation_date,
            ledger=ledger_frame,
            coverage=coverage_frame,
        )
    _ASSEMBLY_BUILD.pop(_stash_key(valuation_date), None)
    return result.data_frame()


def _collect_ledger(
    valuation_date: date,
    source_file: Path | None = None,
    **_kwargs,
) -> pd.DataFrame:
    assembly = _build_and_stash(valuation_date, source_file)
    if assembly.ledger is None or assembly.ledger.empty:
        return pd.DataFrame(columns=list(InstrumentCashFlow.COLUMN_ORDER))
    return assembly.ledger.copy()


def _collect_coverage(
    valuation_date: date,
    source_file: Path | None = None,
    ledger: DataStepFrame | None = None,
    **_kwargs,
) -> pd.DataFrame:
    assembly = _ASSEMBLY_BUILD.get(_stash_key(valuation_date))
    if assembly is None:
        assembly = _build_and_stash(valuation_date, source_file)
    frame = assembly.coverage_frame()
    if frame is None or frame.empty:
        return pd.DataFrame(
            columns=["instrument_id", "status", "reason", "venue", "is_sold"]
        )
    return frame.copy()


def _collect_warnings(
    valuation_date: date,
    source_file: Path | None = None,
    ledger: DataStepFrame | None = None,
    **_kwargs,
) -> pd.DataFrame:
    assembly = _ASSEMBLY_BUILD.get(_stash_key(valuation_date))
    if assembly is None:
        assembly = _build_and_stash(valuation_date, source_file)
    messages = list(assembly.warnings or [])
    if not messages:
        return pd.DataFrame(columns=["message"])
    return pd.DataFrame({"message": messages})


def _collect_xirr(
    valuation_date: date,
    source_file: Path | None = None,
    ledger: DataStepFrame | None = None,
    coverage: DataStepFrame | None = None,
    **_kwargs,
) -> pd.DataFrame:
    ledger_df = (
        ledger.data_frame()
        if isinstance(ledger, DataStepFrame)
        else pd.DataFrame(columns=list(InstrumentCashFlow.COLUMN_ORDER))
    )
    coverage_df = (
        coverage.data_frame()
        if isinstance(coverage, DataStepFrame)
        else pd.DataFrame(
            columns=["instrument_id", "status", "reason", "venue", "is_sold"]
        )
    )
    assembly = _assembly_from_frames(ledger_df, coverage_df)
    snapshot = _read_snapshot(source_file)
    rows: list[dict] = []
    for sold_filter in SOLD_FILTER_LABELS:
        mapping = compute_named_portfolio_metrics_map(
            valuation_date,
            assembly=assembly,
            snapshot=snapshot,
            sold_filter=sold_filter,
        )
        for portfolio, result in mapping.items():
            rows.append(
                {
                    "portfolio": portfolio,
                    "sold_filter": sold_filter,
                    "xirr": result.xirr,
                    "xirr_pln": result.xirr_pln,
                    "roi_pln": result.roi_nominal_pln,
                    "roi_local": result.roi_local_pln,
                    "roi_fx": result.roi_fx_pln,
                    "fx_share": result.fx_share,
                }
            )
    if not rows:
        return pd.DataFrame(columns=list(_XIRR_COLUMNS))
    return pd.DataFrame(rows, columns=list(_XIRR_COLUMNS))


def _build_and_stash(
    valuation_date: date,
    source_file: Path | None,
) -> AssemblyResult:
    snapshot = _read_snapshot(source_file)
    assembly = build_instrument_ledger(valuation_date, snapshot=snapshot)
    _ASSEMBLY_BUILD[_stash_key(valuation_date)] = assembly
    return assembly


def _read_snapshot(source_file: Path | None) -> pd.DataFrame:
    if source_file is None:
        return pd.DataFrame()
    path = Path(source_file)
    if not path.is_file():
        return pd.DataFrame()
    return pd.read_parquet(path)


def _stash_key(valuation_date: date) -> str:
    return valuation_date.isoformat()


def _assembly_from_frames(
    ledger: pd.DataFrame,
    coverage_df: pd.DataFrame,
) -> AssemblyResult:
    coverage: list[InstrumentCoverage] = []
    sold_map: dict[str, bool] = {}
    if coverage_df is not None and not coverage_df.empty:
        for _, row in coverage_df.iterrows():
            instrument_id = str(row.get("instrument_id") or "").strip()
            if not instrument_id:
                continue
            status_raw = str(row.get("status") or CoverageStatus.UNCOVERED.value)
            try:
                status = CoverageStatus(status_raw)
            except ValueError:
                status = CoverageStatus.UNCOVERED
            coverage.append(
                InstrumentCoverage(
                    instrument_id=instrument_id,
                    status=status,
                    reason=str(row.get("reason") or ""),
                    venue=str(row.get("venue") or ""),
                )
            )
            if "is_sold" in coverage_df.columns:
                sold_map[instrument_id] = bool(row.get("is_sold"))
    if ledger is None or ledger.empty:
        ledger = pd.DataFrame(columns=list(InstrumentCashFlow.COLUMN_ORDER))
    return AssemblyResult(
        ledger=ledger,
        coverage=coverage,
        warnings=[],
        is_sold_by_instrument=sold_map,
    )
