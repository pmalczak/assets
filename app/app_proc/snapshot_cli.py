# -*- coding: utf-8 -*-
"""CLI snapshotu w osobnym procesie (Streamlit nie ginie przy crashu native)."""
from __future__ import annotations

import argparse
import faulthandler
import sys
from datetime import date
from pathlib import Path

import pandas as pd

pd.options.future.infer_string = False
faulthandler.enable(all_threads=True)

APP_ROOT = Path(__file__).resolve().parent.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app_proc.data_steps_root import get_data_steps_root
from app_proc.recalculate_snapshots import (
    encode_snapshot_job_results,
    recalculate_today_snapshot,
    recalculate_weekly_snapshots,
)
from data_step.data_step import DATA_STEP


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Przelicz snapshot portfela (proces potomny).")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--today", action="store_true", help="Snapshot na dziś")
    mode.add_argument("--weekly", action="store_true", help="Snapshoty wt/sr/pt/nd z okna ~6 mies.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Wymuś odświeżenie całego cache DATA_STEP (wyciągi + snapshot)",
    )
    parser.add_argument(
        "--reference-date",
        type=date.fromisoformat,
        default=None,
        help="Data końcowa okna weekly (YYYY-MM-DD), domyślnie dziś",
    )
    args = parser.parse_args(argv)

    DATA_STEP.init_steps(root=get_data_steps_root())
    if args.today:
        results = [recalculate_today_snapshot(force_read_all_data=args.force)]
    else:
        results = recalculate_weekly_snapshots(
            force_read_all_data=args.force,
            reference=args.reference_date,
        )
    print(encode_snapshot_job_results(results), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
