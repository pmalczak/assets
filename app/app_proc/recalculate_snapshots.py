# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from app_proc.calculate_assets import assets_snapshot_resource, calculate_assets
from importers.assets.data_model import AssetsDef

TUESDAY = 1
WEDNESDAY = 2
FRIDAY = 4
SUNDAY = 6
SNAPSHOT_WEEKDAYS = (TUESDAY, WEDNESDAY, FRIDAY, SUNDAY)

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


def valuation_dates_one_year_back(reference: date | None = None) -> list[date]:
    end = reference or date.today()
    start = end - timedelta(days=365)

    dates: list[date] = []
    current = start
    while current <= end:
        if current.weekday() in SNAPSHOT_WEEKDAYS:
            dates.append(current)
        current += timedelta(days=1)
    return dates


def _build_snapshot_result(valuation_date: date, assets: pd.DataFrame) -> SnapshotResult:
    total_pln = int(assets[AssetsDef.VALUE_PLN].sum()) if not assets.empty else 0
    return SnapshotResult(
        valuation_date=valuation_date,
        rows=len(assets),
        total_pln=total_pln,
        resource=assets_snapshot_resource(valuation_date),
    )


def recalculate_today_snapshot(*, force_read_all_data: bool = True) -> SnapshotResult:
    valuation_date = date.today()
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
    valuation_dates = valuation_dates_one_year_back(reference)
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
