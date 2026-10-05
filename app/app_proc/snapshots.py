from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pandas as pd

from app_proc.snapshot_step import (
    ASSETS_SNAPSHOT_FILE,
    SNAPSHOT_SCHEMA,
    SNAPSHOTS_STEP,
    assets_snapshot_resource,
)
from app_proc.data_steps_root import get_data_steps_root

SNAPSHOT_DATE_DIR_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2})$")
SNAPSHOT_SCHEMA_DIR = f"s{SNAPSHOT_SCHEMA}"


def snapshots_directory() -> Path:
    return get_data_steps_root() / SNAPSHOTS_STEP


def snapshot_path(snapshot_date: date) -> Path:
    return get_data_steps_root() / assets_snapshot_resource(snapshot_date)


def list_snapshot_files(snapshots_dir: Path) -> list[tuple[date, Path]]:
    if not snapshots_dir.is_dir():
        return []

    result: list[tuple[date, Path]] = []
    for path in snapshots_dir.glob(f"*/{SNAPSHOT_SCHEMA_DIR}/{ASSETS_SNAPSHOT_FILE}"):
        date_dir = path.parent.parent.name
        match = SNAPSHOT_DATE_DIR_PATTERN.fullmatch(date_dir)
        if not match:
            continue
        result.append((date.fromisoformat(match.group(1)), path))
    return sorted(result, key=lambda item: item[0])


def load_snapshot(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)
