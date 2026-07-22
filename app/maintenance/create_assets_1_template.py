# -*- coding: utf-8 -*-
"""
Tworzy plik assets_1.xlsx w katalogu get_online_data_root().

Opcjonalnie kopiuje istniejace zakladki z podanego pliku zrodlowego
(np. dawnego assets.xlsx) i dodaje zakladki zloto-monety-zakupy oraz zloto-monety-ceny.

Uzycie:
  cd app
  uv run python maintenance/create_assets_1_template.py
  uv run python maintenance/create_assets_1_template.py C:/sciezka/assets_1.xlsx
  uv run python maintenance/create_assets_1_template.py C:/sciezka/assets_1.xlsx C:/sciezka/assets.xlsx
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from importers.assets.data_model import (
    AssetsFile,
    GoldCoinInventory,
    GoldCoinUnitPrices,
    GOLD_COIN_INVENTORY_SHEET,
    GOLD_COIN_UNIT_PRICES_SHEET,
    GroupDomain,
    KindDomain,
    TypeDomain,
)
from importers.assets.read_assets import ASSETS_FILE_NAME
from app_proc.data_root import get_online_data_root

_LEGACY_GOLD_VALUATIONS_SHEET = "zloto-monety-wyceny"


def build_gold_coin_sheets() -> dict[str, pd.DataFrame]:
    assets_row = pd.DataFrame(
        [
            {
                AssetsFile.ID: "zloto-monety",
                AssetsFile.TYPE: TypeDomain.GOLD_COINS,
                AssetsFile.GROUP: GroupDomain.GOLD_COINS,
                AssetsFile.DESCR: "Złote monety bulionowe",
                AssetsFile.KIND: f"{KindDomain.ASSETS}.zloto-monety",
                AssetsFile.CURRENCY: "PLN",
                AssetsFile.NOTES: "MTM: inventory (zakupy) × ceny (zloto-monety-ceny)",
            }
        ]
    )

    inventory = pd.DataFrame(
        [
            {
                GoldCoinInventory.DATE: "2024-03-15",
                GoldCoinInventory.COIN: "Krugerrand 1oz",
                GoldCoinInventory.WEIGHT: "1oz",
                GoldCoinInventory.QUANTITY: 1,
                GoldCoinInventory.NOTES: "join CAPEX po dacie (analyse_assets_config)",
            },
            {
                GoldCoinInventory.DATE: "2024-05-10",
                GoldCoinInventory.COIN: "Maple Leaf 1oz",
                GoldCoinInventory.WEIGHT: "1oz",
                GoldCoinInventory.QUANTITY: 1,
                GoldCoinInventory.NOTES: "join CAPEX po dacie (analyse_assets_config)",
            },
        ]
    )

    unit_prices = pd.DataFrame(
        [
            {
                GoldCoinUnitPrices.DATE: "2026-07-01",
                GoldCoinUnitPrices.COIN: "Krugerrand 1oz",
                GoldCoinUnitPrices.UNIT_PRICE: 0,
                GoldCoinUnitPrices.NOTES: "cena jednostkowa (ROI / snapshot MTM)",
            },
            {
                GoldCoinUnitPrices.DATE: "2026-07-01",
                GoldCoinUnitPrices.COIN: "Maple Leaf 1oz",
                GoldCoinUnitPrices.UNIT_PRICE: 0,
                GoldCoinUnitPrices.NOTES: "cena jednostkowa (ROI / snapshot MTM)",
            },
        ]
    )

    return {
        "assets": assets_row,
        GOLD_COIN_INVENTORY_SHEET: inventory,
        GOLD_COIN_UNIT_PRICES_SHEET: unit_prices,
    }


def build_workbook(source_file: Path | None) -> dict[str, pd.DataFrame]:
    gold_sheets = build_gold_coin_sheets()

    if source_file is None or not source_file.is_file():
        return gold_sheets

    existing = pd.read_excel(source_file, sheet_name=None)
    sheets = dict(existing)
    sheets.pop(_LEGACY_GOLD_VALUATIONS_SHEET, None)

    assets = sheets.get("assets")
    if assets is None:
        sheets["assets"] = gold_sheets["assets"]
    elif "zloto-monety" not in assets[AssetsFile.ID].astype(str).tolist():
        sheets["assets"] = pd.concat([assets, gold_sheets["assets"]], ignore_index=True)

    sheets[GOLD_COIN_INVENTORY_SHEET] = gold_sheets[GOLD_COIN_INVENTORY_SHEET]
    if GOLD_COIN_UNIT_PRICES_SHEET not in sheets:
        sheets[GOLD_COIN_UNIT_PRICES_SHEET] = gold_sheets[GOLD_COIN_UNIT_PRICES_SHEET]
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
