# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

from datetime import date

import pandas as pd

from importers.assets.data_model import (
    AssetsDef,
    GoldCoinInventory,
    GroupDomain,
    TypeDomain,
)
from evaluators.valuation_date import filter_excel_rows_on_or_before
from importers.assets.read_assets import read_gold_coin_inventory
from roi.gold_terminal import holdings_from_inventory, resolve_gold_terminal_unrealized


def evaluate_zloto_monety(
    data_root: Path,
    assets_file_row: pd.Series,
    assets_catalog: pd.DataFrame,
    valuation_date: date,
) -> tuple[pd.DataFrame, list[str]]:
    del data_root, assets_catalog  # CAPEX/match bankowy nie tu — analyse_assets_config
    inventory = read_gold_coin_inventory()
    warnings: list[str] = []

    if inventory.empty:
        warnings.append("Brak inventory w zakładce zloto-monety-zakupy.")
    else:
        GoldCoinInventory.check_structure(inventory)

    value_pln, evaluation_date = _resolve_portfolio_value(
        inventory,
        valuation_date,
        warnings,
    )

    assets_row = AssetsDef.as_assets_row(assets_file_row)
    assets_row[AssetsDef.GROUP] = GroupDomain.GOLD_COINS
    assets_row[AssetsDef.TYPE] = TypeDomain.GOLD_COINS
    assets_row[AssetsDef.VALUE] = value_pln
    assets_row[AssetsDef.EVALUATION_DATE] = evaluation_date
    assets_row[AssetsDef.DESCR] = _build_description(inventory, valuation_date)

    result = pd.DataFrame([assets_row])
    AssetsDef.check_structure(result)
    return result, warnings


def _resolve_portfolio_value(
    inventory: pd.DataFrame,
    valuation_date: date,
    warnings: list[str],
) -> tuple[float, str | None]:
    """Σ qty×cena z inventory + zloto-monety-ceny; brak inventory → 0."""
    holdings = holdings_from_inventory(inventory, valuation_date)
    mtm_value, mtm_warnings = resolve_gold_terminal_unrealized(
        valuation_date,
        holdings=holdings,
    )
    warnings.extend(mtm_warnings)
    if holdings:
        return mtm_value, valuation_date.isoformat()

    warnings.append("Brak inventory — wartość = 0.")
    return 0.0, None


def _build_description(inventory: pd.DataFrame, valuation_date: date) -> str:
    if inventory.empty:
        return "inventory: 0"
    filtered = filter_excel_rows_on_or_before(inventory, GoldCoinInventory.DATE, valuation_date)
    return f"inventory wiersze: {len(filtered)}"
