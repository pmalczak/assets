# -*- coding: utf-8 -*-
"""
Migracja arkusza properties -> asset-evaluation w assets_1.xlsx.

Uzycie:
  cd app
  uv run python maintenance/migrate_properties_to_wyceny.py
  uv run python maintenance/migrate_properties_to_wyceny.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

APP_ROOT = Path(__file__).resolve().parent.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app_proc.data_root import get_online_data_root
from importers.assets.data_model import (
    ASSET_EVALUATION_SHEET,
    AssetsFile,
    LEGACY_PROPERTIES_SHEET,
    OperationDomain,
    Properties,
    PropertyValuations,
)
from importers.assets.property_lifecycle import load_property_close_dates
from roi.config import read_analyse_config

KIND_PROPERTIES_WYCENY = "assets.properties-wyceny"


def migrate_assets_file(target: Path, *, dry_run: bool = False) -> list[str]:
    messages: list[str] = []
    xl = pd.ExcelFile(target)
    sheets = {name: pd.read_excel(target, sheet_name=name) for name in xl.sheet_names}

    if LEGACY_PROPERTIES_SHEET not in sheets:
        messages.append(f"Pominieto: brak arkusza {LEGACY_PROPERTIES_SHEET!r}.")
        return messages

    legacy = sheets[LEGACY_PROPERTIES_SHEET]
    Properties.check_structure(legacy, file=target)

    open_rows = legacy[legacy[Properties.OPERATION] != OperationDomain.SOLD].copy()
    sold_rows = legacy[legacy[Properties.OPERATION] == OperationDomain.SOLD].copy()

    if ASSET_EVALUATION_SHEET in sheets:
        wyceny = sheets[ASSET_EVALUATION_SHEET]
        PropertyValuations.check_structure(wyceny, file=target)
        wyceny = pd.concat([wyceny, open_rows], ignore_index=True)
        wyceny = wyceny.drop_duplicates(
            subset=[Properties.ID, Properties.DATE, Properties.OPERATION, Properties.VALUE],
            keep="first",
        )
    else:
        wyceny = open_rows.copy()

    wyceny = wyceny.sort_values([Properties.ID, Properties.DATE]).reset_index(drop=True)
    sheets[ASSET_EVALUATION_SHEET] = wyceny
    messages.append(
        f"Arkusz {ASSET_EVALUATION_SHEET!r}: {len(wyceny)} wierszy "
        f"(bez operacja=sprzedane)."
    )

    config = read_analyse_config()
    close_dates = load_property_close_dates(config["manual"], config["catalog"])
    for _, row in sold_rows.iterrows():
        properties_id = str(row[Properties.ID])
        sold_date = pd.Timestamp(row[Properties.DATE]).date()
        close_date = close_dates.get(properties_id)
        if close_date is None:
            messages.append(
                f"OSTRZEZENIE: {properties_id!r} sprzedane {sold_date} — brak DIVESTMENT w ROI manual."
            )
        elif close_date != sold_date:
            messages.append(
                f"OSTRZEZENIE: {properties_id!r} sprzedane {sold_date}, "
                f"DIVESTMENT w ROI manual {close_date}."
            )
        else:
            messages.append(f"OK: {properties_id!r} DIVESTMENT zgodny z data sprzedazy {sold_date}.")

    assets = sheets.get("assets")
    if assets is not None:
        AssetsFile.check_structure(assets)
        mask = assets[AssetsFile.KIND] == "assets.properties"
        if mask.any():
            assets.loc[mask, AssetsFile.KIND] = KIND_PROPERTIES_WYCENY
            sheets["assets"] = assets
            messages.append(f"Zaktualizowano RODZAJ* -> {KIND_PROPERTIES_WYCENY!r} ({int(mask.sum())} wiersz/y).")

    if dry_run:
        messages.append("Dry-run: plik nie zostal zapisany.")
        return messages

    with pd.ExcelWriter(target, engine="openpyxl") as writer:
        for sheet_name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=sheet_name, index=False)

    messages.append(f"Zapisano: {target.resolve()}")
    return messages


def main() -> None:
    parser = argparse.ArgumentParser(description="Migracja properties -> asset-evaluation")
    parser.add_argument(
        "target",
        nargs="?",
        default=str(get_online_data_root() / "a_config.xlsx"),
        help="Ścieżka do a_config.xlsx",
    )
    parser.add_argument("--dry-run", action="store_true", help="Tylko raport, bez zapisu")
    args = parser.parse_args()

    target = Path(args.target)
    assert target.is_file(), target

    for line in migrate_assets_file(target, dry_run=args.dry_run):
        print(line)


if __name__ == "__main__":
    main()
