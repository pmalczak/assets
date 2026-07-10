# -*- coding: utf-8 -*-
"""
Przelicza calculate_assets() we wtorki, srody, piatki i niedziele w oknie 365 dni wstecz od dzis.

Wyniki trafiaja do data_steps/09 assets/YYYY-MM-DD.parquet (krok DATA_STEP).

Uzycie:
  cd app
  uv run python maintenance/recalculate_weekly_assets_snapshots.py
  uv run python maintenance/recalculate_weekly_assets_snapshots.py --force
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

GITHUB_COMMON_ROOT = Path.home() / "PycharmProjects" / "github_common_py"
if str(GITHUB_COMMON_ROOT) not in sys.path:
    sys.path.append(str(GITHUB_COMMON_ROOT))

from main_proc.calculate_assets import (
    PORTFOLIO_VALUATION_DATE,
    assets_snapshot_resource,
    calculate_assets,
)


TUESDAY = 1
WEDNESDAY = 2
FRIDAY = 4
SUNDAY = 6
SNAPSHOT_WEEKDAYS = (TUESDAY, WEDNESDAY, FRIDAY, SUNDAY)


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


def sundays_one_year_back(reference: date | None = None) -> list[date]:
    """Alias zachowany dla kompatybilnosci; uzyj valuation_dates_one_year_back()."""
    return valuation_dates_one_year_back(reference)


def recalculate_weekly_assets_snapshots(
    reference: date | None = None,
    force_read_all_data: bool = False,
) -> list[tuple[date, int, str]]:
    valuation_dates = valuation_dates_one_year_back(reference)
    results: list[tuple[date, int, str]] = []

    for index, valuation_date in enumerate(valuation_dates):
        use_force = force_read_all_data and index == 0
        assets = calculate_assets(
            valuation_date=valuation_date,
            force_read_all_data=use_force,
        )
        resource = assets_snapshot_resource(valuation_date)
        total_pln = int(assets["wartość-pln"].sum()) if not assets.empty else 0
        results.append((valuation_date, len(assets), resource))
        print(
            f"{valuation_date:%Y-%m-%d}  wiersze={len(assets):3d}  "
            f"suma_pln={total_pln:>12,}  {resource}"
        )

    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Przelicz snapshoty portfela (09 assets) we wtorki, srody, piatki i niedziele z ostatniego roku.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Wymus odswiezenie cache DATA_STEP przy pierwszym wyliczeniu",
    )
    parser.add_argument(
        "--reference-date",
        type=date.fromisoformat,
        default=None,
        help="Data koncowa okna (domyslnie dzis), format YYYY-MM-DD",
    )
    args = parser.parse_args()

    reference = args.reference_date or date.today()
    dates = valuation_dates_one_year_back(reference)
    print(f"Okno: {reference - timedelta(days=365):%Y-%m-%d} .. {reference:%Y-%m-%d}")
    print(f"Dat wyceny (wt, sr, pt, nd): {len(dates)}")
    print(f"Kolumna daty snapshotu: {PORTFOLIO_VALUATION_DATE}")
    print()

    recalculate_weekly_assets_snapshots(
        reference=reference,
        force_read_all_data=args.force,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
