# -*- coding: utf-8 -*-
"""
Przelicza calculate_assets() we wtorki, srody, piatki i niedziele
w oknie PORTFOLIO_WINDOW_DAYS (~6 mies.) wstecz od dzis.

Wyniki trafiaja do data_steps/ASSETS_SNAPSHOT_STEP/YYYY-MM-DD.parquet (krok DATA_STEP).

Uzycie:
  cd app
  uv run python maintenance/recalculate_weekly_assets_snapshots.py
  uv run python maintenance/recalculate_weekly_assets_snapshots.py --force
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

from data_step.data_step import DATA_STEP
from app_proc.calculate_assets import PORTFOLIO_VALUATION_DATE, ASSETS_SNAPSHOT_STEP
from app_proc.recalculate_snapshots import (
    PORTFOLIO_WINDOW_DAYS,
    recalculate_weekly_snapshots,
    valuation_dates_in_window,
)


def main() -> int:
    local_data_steps_root = Path(__file__)
    DATA_STEP.init_steps(root=local_data_steps_root)

    parser = argparse.ArgumentParser(
        description=(
            f"Przelicz snapshoty portfela ({ASSETS_SNAPSHOT_STEP}) we wtorki, srody, "
            f"piatki i niedziele z ostatnich ~6 miesiecy ({PORTFOLIO_WINDOW_DAYS} dni)."
        ),
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
    dates = valuation_dates_in_window(reference)
    print(
        f"Okno: {reference - timedelta(days=PORTFOLIO_WINDOW_DAYS):%Y-%m-%d} "
        f".. {reference:%Y-%m-%d}"
    )
    print(f"Dat wyceny (wt, sr, pt, nd): {len(dates)}")
    print(f"Kolumna daty snapshotu: {PORTFOLIO_VALUATION_DATE}")
    print()

    results = recalculate_weekly_snapshots(
        reference=reference,
        force_read_all_data=args.force,
    )
    for result in results:
        print(
            f"{result.valuation_date:%Y-%m-%d}  wiersze={result.rows:3d}  "
            f"suma_pln={result.total_pln:>12,}  {result.resource}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
