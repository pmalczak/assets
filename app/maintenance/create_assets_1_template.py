# -*- coding: utf-8 -*-
"""
Tworzy plik assets_1.xlsx w katalogu get_online_data_root().

Opcjonalnie kopiuje istniejace zakladki z podanego pliku zrodlowego
(np. dawnego assets.xlsx) i dodaje zakladki zloto-monety-zakupy oraz zloto-monety-wyceny.

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
    GoldCoinPurchaseRules,
    GoldCoinUnitPrices,
    GoldCoinValuations,
    GOLD_COIN_PURCHASES_SHEET,
    GOLD_COIN_UNIT_PRICES_SHEET,
    GOLD_COIN_VALUATIONS_SHEET,
    GroupDomain,
    KindDomain,
    TypeDomain,
)
from importers.assets.read_assets import ASSETS_FILE_NAME
from app_proc.data_root import get_online_data_root


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
                AssetsFile.NOTES: "wycena manualna w osobnej zakladce",
            }
        ]
    )

    purchases = pd.DataFrame(
        [
            {
                GoldCoinPurchaseRules.RULE_ID: "km-przyklad",
                GoldCoinPurchaseRules.SOURCE_ACCOUNT: "p_m_34_9142",
                GoldCoinPurchaseRules.DATE: "2024-03-15",
                GoldCoinPurchaseRules.DATE_FROM: pd.NA,
                GoldCoinPurchaseRules.DATE_TO: pd.NA,
                GoldCoinPurchaseRules.TITLE: "MENNICA",
                GoldCoinPurchaseRules.TITLE_MATCH: "contains",
                GoldCoinPurchaseRules.COUNTERPARTY: "MENNICA",
                GoldCoinPurchaseRules.COUNTERPARTY_IBAN: "PL61102010260000042270201111",
                GoldCoinPurchaseRules.AMOUNT: -15000,
                GoldCoinPurchaseRules.AMOUNT_TOLERANCE: 0.01,
                GoldCoinPurchaseRules.OPERATION_DESCRIPTION: "PRZELEW ZEWNĘTRZNY WYCHODZĄCY",
                GoldCoinPurchaseRules.COIN: "Krugerrand 1oz",
                GoldCoinPurchaseRules.QUANTITY: 1,
                GoldCoinPurchaseRules.WEIGHT: "1oz",
                GoldCoinPurchaseRules.NOTES: "przyklad reguly mbank",
            },
            {
                GoldCoinPurchaseRules.RULE_ID: "km-revolut-przyklad",
                GoldCoinPurchaseRules.SOURCE_ACCOUNT: "p_re_eur",
                GoldCoinPurchaseRules.DATE: "2024-05-10",
                GoldCoinPurchaseRules.DATE_FROM: pd.NA,
                GoldCoinPurchaseRules.DATE_TO: pd.NA,
                GoldCoinPurchaseRules.TITLE: "Gold purchase",
                GoldCoinPurchaseRules.TITLE_MATCH: "contains",
                GoldCoinPurchaseRules.COUNTERPARTY: pd.NA,
                GoldCoinPurchaseRules.COUNTERPARTY_IBAN: pd.NA,
                GoldCoinPurchaseRules.AMOUNT: -4000,
                GoldCoinPurchaseRules.AMOUNT_TOLERANCE: 0.01,
                GoldCoinPurchaseRules.OPERATION_DESCRIPTION: pd.NA,
                GoldCoinPurchaseRules.COIN: "Maple Leaf 1oz",
                GoldCoinPurchaseRules.QUANTITY: 1,
                GoldCoinPurchaseRules.WEIGHT: "1oz",
                GoldCoinPurchaseRules.NOTES: "przyklad reguly revolut",
            },
        ]
    )

    valuations = pd.DataFrame(
        [
            {
                GoldCoinValuations.DATE: "2026-07-01",
                GoldCoinValuations.VALUE: 0,
                GoldCoinValuations.NOTES: "uzupelnij reczna wycene calego holdingu",
            }
        ]
    )

    unit_prices = pd.DataFrame(
        [
            {
                GoldCoinUnitPrices.DATE: "2026-07-01",
                GoldCoinUnitPrices.COIN: "Krugerrand 1oz",
                GoldCoinUnitPrices.UNIT_PRICE: 0,
                GoldCoinUnitPrices.NOTES: "cena jednostkowa (ROI mark-to-market)",
            },
            {
                GoldCoinUnitPrices.DATE: "2026-07-01",
                GoldCoinUnitPrices.COIN: "Maple Leaf 1oz",
                GoldCoinUnitPrices.UNIT_PRICE: 0,
                GoldCoinUnitPrices.NOTES: "cena jednostkowa (ROI mark-to-market)",
            },
        ]
    )

    return {
        "assets": assets_row,
        GOLD_COIN_PURCHASES_SHEET: purchases,
        GOLD_COIN_VALUATIONS_SHEET: valuations,
        GOLD_COIN_UNIT_PRICES_SHEET: unit_prices,
    }


def build_workbook(source_file: Path | None) -> dict[str, pd.DataFrame]:
    gold_sheets = build_gold_coin_sheets()

    if source_file is None or not source_file.is_file():
        return gold_sheets

    existing = pd.read_excel(source_file, sheet_name=None)
    sheets = dict(existing)

    assets = sheets.get("assets")
    if assets is None:
        sheets["assets"] = gold_sheets["assets"]
    elif "zloto-monety" not in assets[AssetsFile.ID].astype(str).tolist():
        sheets["assets"] = pd.concat([assets, gold_sheets["assets"]], ignore_index=True)

    sheets[GOLD_COIN_PURCHASES_SHEET] = gold_sheets[GOLD_COIN_PURCHASES_SHEET]
    sheets[GOLD_COIN_VALUATIONS_SHEET] = gold_sheets[GOLD_COIN_VALUATIONS_SHEET]
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
