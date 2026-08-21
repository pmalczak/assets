# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from app_proc.calculate_assets import assets_snapshot_resource, calculate_assets
from data_step.data_step import DATA_STEP
from importers.assets.data_model import AssetsDef

APP_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_JOB_RESULT_PREFIX = "SNAPSHOT_JOB_RESULT_V1:"

TUESDAY = 1
WEDNESDAY = 2
FRIDAY = 4
SUNDAY = 6
SNAPSHOT_WEEKDAYS = (TUESDAY, WEDNESDAY, FRIDAY, SUNDAY)
PORTFOLIO_WINDOW_DAYS = 183  # ~6 months — wykres portfela i pełne przeliczenie snapshotów

SNAPSHOT_DISPLAY_COLUMNS = {
    "valuation_date": "Data wyceny",
    "rows": "Wiersze",
    "total_pln": "Suma PLN",
    "resource": "Plik snapshotu",
}


@dataclass(frozen=True)
class SnapshotResult:
    valuation_date: date
    rows: int
    total_pln: int
    resource: str

    def to_row(self) -> dict[str, object]:
        return {
            "valuation_date": self.valuation_date.isoformat(),
            "rows": self.rows,
            "total_pln": self.total_pln,
            "resource": self.resource,
        }


def valuation_dates_in_window(
    reference: date | None = None,
    *,
    days: int = PORTFOLIO_WINDOW_DAYS,
) -> list[date]:
    end = reference or date.today()
    start = end - timedelta(days=days)

    dates: list[date] = []
    current = start
    while current <= end:
        if current.weekday() in SNAPSHOT_WEEKDAYS:
            dates.append(current)
        current += timedelta(days=1)
    return dates


# Alias historyczny — to samo okno co valuation_dates_in_window.
valuation_dates_one_year_back = valuation_dates_in_window


def _build_snapshot_result(valuation_date: date, assets: pd.DataFrame) -> SnapshotResult:
    total_pln = int(assets[AssetsDef.VALUE_PLN].sum()) if not assets.empty else 0
    return SnapshotResult(
        valuation_date=valuation_date,
        rows=len(assets),
        total_pln=total_pln,
        resource=assets_snapshot_resource(valuation_date),
    )


def recalculate_today_snapshot(*, force_read_all_data: bool = False) -> SnapshotResult:
    valuation_date = date.today()
    if not force_read_all_data:
        # Bez globalnego force: przebuduj tylko snapshot na dziś, źródła zostaw z DATA_STEP.
        DATA_STEP.invalidate(assets_snapshot_resource(valuation_date))
    assets = calculate_assets(
        valuation_date=valuation_date,
        force_read_all_data=force_read_all_data,
    )
    return _build_snapshot_result(valuation_date, assets)


def recalculate_weekly_snapshots(
    *,
    force_read_all_data: bool = True,
    reference: date | None = None,
) -> list[SnapshotResult]:
    valuation_dates = valuation_dates_in_window(reference)
    results: list[SnapshotResult] = []

    for index, valuation_date in enumerate(valuation_dates):
        use_force = force_read_all_data and index == 0
        assets = calculate_assets(
            valuation_date=valuation_date,
            force_read_all_data=use_force,
        )
        results.append(_build_snapshot_result(valuation_date, assets))

    return results


def snapshot_results_to_dataframe(results: list[SnapshotResult]) -> pd.DataFrame:
    if not results:
        return pd.DataFrame(columns=list(SNAPSHOT_DISPLAY_COLUMNS.keys()))

    df = pd.DataFrame([result.to_row() for result in results])
    return df[list(SNAPSHOT_DISPLAY_COLUMNS.keys())].rename(columns=SNAPSHOT_DISPLAY_COLUMNS)


def _result_from_row(row: dict[str, object]) -> SnapshotResult:
    return SnapshotResult(
        valuation_date=date.fromisoformat(str(row["valuation_date"])),
        rows=int(row["rows"]),
        total_pln=int(row["total_pln"]),
        resource=str(row["resource"]),
    )


def encode_snapshot_job_results(results: list[SnapshotResult]) -> str:
    payload = {"results": [result.to_row() for result in results]}
    return SNAPSHOT_JOB_RESULT_PREFIX + json.dumps(payload, ensure_ascii=False)


def parse_snapshot_job_stdout(stdout: str) -> list[SnapshotResult]:
    for line in reversed(stdout.splitlines()):
        if line.startswith(SNAPSHOT_JOB_RESULT_PREFIX):
            payload = json.loads(line[len(SNAPSHOT_JOB_RESULT_PREFIX) :])
            return [_result_from_row(item) for item in payload["results"]]
    raise RuntimeError(
        "Proces snapshotu nie zwrócił markera wyniku. "
        f"Ostatnie logi:\n{stdout[-4000:]}"
    )


def _format_snapshot_job_failure(proc: subprocess.CompletedProcess[str]) -> str:
    rc = proc.returncode
    crashed = rc in (-signal.SIGSEGV, 139)
    header = (
        f"Proces przeliczania snapshotu zakończył się kodem {rc}"
        + (" (segfault / błąd native — Streamlit został ochroniony)." if crashed else ".")
    )
    chunks = [header]
    if proc.stderr:
        chunks.append("stderr:\n" + proc.stderr[-4000:])
    if proc.stdout:
        chunks.append("stdout:\n" + proc.stdout[-4000:])
    return "\n\n".join(chunks)


def run_snapshot_job_isolated(
    *,
    weekly: bool = False,
    force_read_all_data: bool = False,
    reference: date | None = None,
) -> list[SnapshotResult]:
    """Przelicza snapshot w osobnym procesie — crash pyarrow nie zabija Streamlit."""
    cmd = [sys.executable, "-m", "app_proc.snapshot_cli"]
    cmd.append("--weekly" if weekly else "--today")
    if force_read_all_data:
        cmd.append("--force")
    if reference is not None:
        cmd.extend(["--reference-date", reference.isoformat()])

    env = os.environ.copy()
    env["PYTHONFAULTHANDLER"] = "1"
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(APP_ROOT) + (os.pathsep + existing if existing else "")

    proc = subprocess.run(
        cmd,
        cwd=str(APP_ROOT),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(_format_snapshot_job_failure(proc))
    return parse_snapshot_job_stdout(proc.stdout)
