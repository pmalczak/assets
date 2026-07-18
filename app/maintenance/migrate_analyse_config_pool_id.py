# -*- coding: utf-8 -*-
"""
Migracja analyse_assets_config.xlsx: kolumna source → pool_id (catalog + rules).

Użycie:
  cd app
  uv run python maintenance/migrate_analyse_config_pool_id.py
  uv run python maintenance/migrate_analyse_config_pool_id.py C:/sciezka/analyse_assets_config.xlsx
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

APP_ROOT = Path(__file__).resolve().parent.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from analyse_assets.config_model import (
    CONFIG_FILE_NAME,
    CATALOG_SHEET,
    MANUAL_SHEET,
    RULES_SHEET,
)
from app_proc.data_root import get_online_data_root


def _rename_source_to_pool_id(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "pool_id" not in df.columns and "source" in df.columns:
        return df.rename(columns={"source": "pool_id"})
    if "pool_id" in df.columns and "source" in df.columns:
        blank = df["pool_id"].isna() | (df["pool_id"].astype(str).str.strip() == "")
        df.loc[blank, "pool_id"] = df.loc[blank, "source"]
        return df.drop(columns=["source"])
    if "pool_id" not in df.columns:
        df["pool_id"] = ""
    return df


def migrate(path: Path) -> Path:
    catalog = _rename_source_to_pool_id(pd.read_excel(path, sheet_name=CATALOG_SHEET))
    rules = _rename_source_to_pool_id(pd.read_excel(path, sheet_name=RULES_SHEET))
    manual = pd.read_excel(path, sheet_name=MANUAL_SHEET)

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        catalog.to_excel(writer, sheet_name=CATALOG_SHEET, index=False)
        rules.to_excel(writer, sheet_name=RULES_SHEET, index=False)
        manual.to_excel(writer, sheet_name=MANUAL_SHEET, index=False)
    return path


def main() -> None:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else get_online_data_root() / CONFIG_FILE_NAME
    assert target.is_file(), target
    migrate(target)
    print(f"Zmigrowano source→pool_id: {target.resolve()}")


if __name__ == "__main__":
    main()
