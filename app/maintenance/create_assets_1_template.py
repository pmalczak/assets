# -*- coding: utf-8 -*-
"""
Tworzy minimalny szablon arkuszy portfela (assets / inventory / unit-price-evaluation).

Uwaga: zapisuje tylko arkusze portfela. Nie używaj na pełnym a_config.xlsx
z arkuszami ROI — podaj osobną ścieżkę lub użyj migrate_to_a_config.

Użycie:
  cd app
  uv run python maintenance/create_assets_1_template.py C:/tmp/portfolio_template.xlsx
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from importers.assets.data_model import (
    AssetsFile,
    INVENTORY_SHEET,
    INSTRUMENTS_SHEET,
    Inventory,
    LEGACY_INVENTORY_SHEET,
    LEGACY_UNIT_PRICE_EVALUATION_SHEET,
    UNIT_PRICE_EVALUATION_SHEET,
    UnitPriceEvaluation,
    GroupDomain,
    KindDomain,
    TypeDomain,
)
from importers.assets.instruments import empty_instruments_table
from importers.assets.read_assets import ASSETS_FILE_NAME
from app_proc.data_root import get_online_data_root


def build_inventory_sheets() -> dict[str, pd.DataFrame]:
    assets_row = pd.DataFrame(
        [
            {
                AssetsFile.ID: "zloto-monety",
                AssetsFile.TYPE: TypeDomain.GOLD_COINS,
                AssetsFile.GROUP: GroupDomain.GOLD_COINS,
                AssetsFile.DESCR: "Złote monety bulionowe",
                AssetsFile.KIND: f"{KindDomain.ASSETS}.zloto-monety",
                AssetsFile.CURRENCY: "PLN",
                AssetsFile.NOTES: "MTM: inventory × ceny (unit-price-evaluation)",
            }
        ]
    )

    inventory = pd.DataFrame(
        [
            {
                Inventory.DATE: "2024-03-15",
                Inventory.INSTRUMENT: "Krugerrand 1oz",
                Inventory.WEIGHT: "1oz",
                Inventory.QUANTITY: 1,
                Inventory.NOTES: "join CAPEX po dacie (a_config / roi_rules)",
            },
            {
                Inventory.DATE: "2024-05-10",
                Inventory.INSTRUMENT: "Maple Leaf 1oz",
                Inventory.WEIGHT: "1oz",
                Inventory.QUANTITY: 1,
                Inventory.NOTES: "join CAPEX po dacie (a_config / roi_rules)",
            },
        ]
    )

    unit_prices = pd.DataFrame(
        [
            {
                UnitPriceEvaluation.DATE: "2026-07-01",
                UnitPriceEvaluation.INSTRUMENT: "Krugerrand 1oz",
                UnitPriceEvaluation.UNIT_PRICE: 0,
                UnitPriceEvaluation.NOTES: "cena jednostkowa (ROI / snapshot MTM)",
            },
            {
                UnitPriceEvaluation.DATE: "2026-07-01",
                UnitPriceEvaluation.INSTRUMENT: "Maple Leaf 1oz",
                UnitPriceEvaluation.UNIT_PRICE: 0,
                UnitPriceEvaluation.NOTES: "cena jednostkowa (ROI / snapshot MTM)",
            },
        ]
    )

    return {
        "assets": assets_row,
        INVENTORY_SHEET: inventory,
        INSTRUMENTS_SHEET: empty_instruments_table(),
        UNIT_PRICE_EVALUATION_SHEET: unit_prices,
    }


def build_workbook(source_file: Path | None) -> dict[str, pd.DataFrame]:
    template_sheets = build_inventory_sheets()

    if source_file is None or not source_file.is_file():
        return template_sheets

    existing = pd.read_excel(source_file, sheet_name=None)
    sheets = dict(existing)
    sheets.pop(LEGACY_INVENTORY_SHEET, None)
    sheets.pop(LEGACY_UNIT_PRICE_EVALUATION_SHEET, None)

    assets = sheets.get("assets")
    if assets is None:
        sheets["assets"] = template_sheets["assets"]
    elif "zloto-monety" not in assets[AssetsFile.ID].astype(str).tolist():
        sheets["assets"] = pd.concat([assets, template_sheets["assets"]], ignore_index=True)

    sheets[INVENTORY_SHEET] = template_sheets[INVENTORY_SHEET]
    if INSTRUMENTS_SHEET not in sheets:
        sheets[INSTRUMENTS_SHEET] = template_sheets[INSTRUMENTS_SHEET]
    if UNIT_PRICE_EVALUATION_SHEET not in sheets:
        sheets[UNIT_PRICE_EVALUATION_SHEET] = template_sheets[UNIT_PRICE_EVALUATION_SHEET]
    return sheets


def main() -> None:
    data_root = get_online_data_root()
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else data_root / ASSETS_FILE_NAME
    source_file = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    if source_file is None or not source_file.is_file():
        if source_file is not None:
            print(f"Uwaga: brak {source_file}; tworze minimalny szablon.")
        else:
            print(f"Tworze minimalny szablon {ASSETS_FILE_NAME}.")
        sheets = build_workbook(None)
    else:
        print(f"Migracja z: {source_file}")
        sheets = build_workbook(source_file)

    with pd.ExcelWriter(target, engine="openpyxl") as writer:
        for sheet_name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=sheet_name, index=False)

    print(f"Utworzono: {target.resolve()}")


if __name__ == "__main__":
    main()
