# -*- coding: utf-8 -*-
"""
Przenosi katalogi aktywów typ=cash_pool.* z INWESTYCJE/assets do INWESTYCJE/cash_pool.

Użycie:
  cd app
  uv run python maintenance/migrate_cash_pool_dirs.py --dry-run
  uv run python maintenance/migrate_cash_pool_dirs.py
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from app_proc.data_root import get_cash_pool_root, get_online_data_root
from importers.assets.data_model import AssetsFile
from importers.assets.read_assets import ASSETS_FILE_NAME, get_assets_file


@dataclass(frozen=True)
class MigrateResult:
    asset_id: str
    action: str
    source: Path | None
    destination: Path | None


def cash_pool_asset_ids(assets: pd.DataFrame) -> list[str]:
    typ = assets[AssetsFile.TYPE].astype(str)
    mask = typ.str.startswith("cash_pool.")
    return assets.loc[mask, AssetsFile.ID].astype(str).tolist()


def migrate_cash_pool_dirs(
    *,
    assets_root: Path | None = None,
    cash_pool_root: Path | None = None,
    assets: pd.DataFrame | None = None,
    dry_run: bool = False,
) -> list[MigrateResult]:
    assets_root = assets_root or get_online_data_root()
    cash_pool_root = cash_pool_root or get_cash_pool_root()
    if assets is None:
        assets = pd.read_excel(get_assets_file(), sheet_name="assets")

    if not dry_run:
        cash_pool_root.mkdir(parents=True, exist_ok=True)

    results: list[MigrateResult] = []
    for asset_id in cash_pool_asset_ids(assets):
        source = assets_root / asset_id
        destination = cash_pool_root / asset_id

        if destination.exists():
            results.append(
                MigrateResult(asset_id, "pominięty (cel istnieje)", source if source.exists() else None, destination)
            )
            continue
        if not source.is_dir():
            results.append(MigrateResult(asset_id, "brak źródła", None, destination))
            continue

        if dry_run:
            results.append(MigrateResult(asset_id, "dry-run (do przeniesienia)", source, destination))
            continue

        source.replace(destination)
        results.append(MigrateResult(asset_id, "przeniesiony", source, destination))

    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description=f"Przenieś katalogi cash_pool.* z assets/ do cash_pool/ (wg {ASSETS_FILE_NAME}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Tylko wypisz plan, bez przenoszenia plików",
    )
    args = parser.parse_args()

    results = migrate_cash_pool_dirs(dry_run=args.dry_run)
    for result in results:
        src = result.source if result.source is not None else "—"
        dst = result.destination if result.destination is not None else "—"
        print(f"{result.action}: {result.asset_id}  {src} -> {dst}")

    moved = sum(1 for r in results if r.action in {"przeniesiony", "dry-run (do przeniesienia)"})
    print(f"\nRazem: {len(results)} (do przeniesienia/przeniesione: {moved})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
