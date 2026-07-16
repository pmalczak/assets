from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pandas as pd

from app_proc.calculate_assets import ASSETS_SNAPSHOT_STEP, PORTFOLIO_VALUATION_DATE
from app_proc.data_steps_root import get_data_steps_root

SNAPSHOT_DATE_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2})\.parquet$")


def snapshots_directory() -> Path:
    return get_data_steps_root() / ASSETS_SNAPSHOT_STEP


def list_snapshot_files(snapshots_dir: Path) -> list[tuple[date, Path]]:
    if not snapshots_dir.is_dir():
        return []

    result: list[tuple[date, Path]] = []
    for path in snapshots_dir.glob("*.parquet"):
        match = SNAPSHOT_DATE_PATTERN.match(path.name)
        if not match:
            continue
        result.append((date.fromisoformat(match.group(1)), path))
    return sorted(result, key=lambda item: item[0])


def load_snapshot(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    if PORTFOLIO_VALUATION_DATE not in df.columns:
        valuation_date = date.fromisoformat(path.stem)
        df = df.copy()
        df[PORTFOLIO_VALUATION_DATE] = valuation_date.isoformat()
    return df
