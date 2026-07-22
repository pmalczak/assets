# -*- coding: utf-8 -*-
"""Terminal ROI dla złoto-monety: Σ sztuki × cena_jednostkowa."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from evaluators.valuation_date import filter_excel_rows_on_or_before
from importers.assets.data_model import GoldCoinPurchaseRules, GoldCoinUnitPrices
from importers.assets.match_bank_transaction import RuleMatchOutcome
from importers.assets.read_assets import read_assets, read_gold_coin_purchase_rules, read_gold_coin_unit_prices

GOLD_COINS_ROI_ASSET_ID = "zloto-monety"


def is_gold_roi_asset(asset_id: str | None, properties_id: str | None = None) -> bool:
    return (properties_id or asset_id) == GOLD_COINS_ROI_ASSET_ID


def holdings_from_outcomes(
    outcomes: list[RuleMatchOutcome],
    purchase_rules: pd.DataFrame,
) -> dict[str, float]:
    """Zsumuj sztuki z dopasowanych reguł zakupu (metadata moneta/sztuki)."""
    if purchase_rules.empty or not outcomes:
        return {}

    by_rule = purchase_rules.set_index(GoldCoinPurchaseRules.RULE_ID, drop=False)
    holdings: dict[str, float] = {}
    for outcome in outcomes:
        if outcome.status != "ok":
            continue
        if outcome.rule_id not in by_rule.index:
            continue
        row = by_rule.loc[outcome.rule_id]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        coin = str(row[GoldCoinPurchaseRules.COIN]).strip()
        qty = float(row[GoldCoinPurchaseRules.QUANTITY])
        if not coin or pd.isna(qty):
            continue
        holdings[coin] = holdings.get(coin, 0.0) + qty
    return holdings


def latest_unit_price(
    unit_prices: pd.DataFrame,
    coin: str,
    valuation_date: date,
) -> float | None:
    if unit_prices is None or unit_prices.empty:
        return None

    filtered = filter_excel_rows_on_or_before(unit_prices, GoldCoinUnitPrices.DATE, valuation_date)
    if filtered.empty:
        return None

    coin_rows = filtered[
        filtered[GoldCoinUnitPrices.COIN].astype("string").str.strip() == coin
    ]
    if coin_rows.empty:
        return None

    latest = coin_rows.sort_values(GoldCoinUnitPrices.DATE, ascending=False).iloc[0]
    price = pd.to_numeric(latest[GoldCoinUnitPrices.UNIT_PRICE], errors="coerce")
    if pd.isna(price):
        return None
    return float(price)


def mark_to_market(
    holdings: dict[str, float],
    unit_prices: pd.DataFrame,
    valuation_date: date,
) -> tuple[float, list[str]]:
    """Σ qty × cena; brak ceny → warning i 0 dla tej monety."""
    warnings: list[str] = []
    if not holdings:
        return 0.0, warnings

    total = 0.0
    for coin, qty in holdings.items():
        price = latest_unit_price(unit_prices, coin, valuation_date)
        if price is None:
            warnings.append(
                f"Brak ceny jednostkowej dla monety {coin!r} na date {valuation_date}."
            )
            continue
        total += qty * price
    return total, warnings


def resolve_gold_terminal_unrealized(
    valuation_date: date,
    *,
    holdings: dict[str, float] | None = None,
    unit_prices: pd.DataFrame | None = None,
    outcomes: list[RuleMatchOutcome] | None = None,
    purchase_rules: pd.DataFrame | None = None,
    data_root: Path | None = None,
    assets_catalog: pd.DataFrame | None = None,
) -> tuple[float, list[str]]:
    """
    Terminal unrealized dla złoto-monety.

    Testy mogą podać `holdings` + `unit_prices` bezpośrednio.
    Produkcja buduje stan z dopasowanych zakupów i arkusza zloto-monety-ceny.
    """
    warnings: list[str] = []

    if holdings is None:
        if purchase_rules is None:
            purchase_rules = read_gold_coin_purchase_rules()
        if outcomes is None:
            outcomes, match_warnings = _match_purchases(
                valuation_date,
                purchase_rules,
                data_root=data_root,
                assets_catalog=assets_catalog,
            )
            warnings.extend(match_warnings)
        holdings = holdings_from_outcomes(outcomes, purchase_rules)

    if unit_prices is None:
        unit_prices = read_gold_coin_unit_prices()
        if unit_prices.empty:
            warnings.append(
                "Brak arkusza zloto-monety-ceny (ceny jednostkowe) — terminal = 0."
            )
            return 0.0, warnings

    if not unit_prices.empty:
        GoldCoinUnitPrices.check_structure(unit_prices)

    value, mtm_warnings = mark_to_market(holdings, unit_prices, valuation_date)
    warnings.extend(mtm_warnings)
    return value, warnings


def _match_purchases(
    valuation_date: date,
    purchase_rules: pd.DataFrame,
    *,
    data_root: Path | None,
    assets_catalog: pd.DataFrame | None,
) -> tuple[list[RuleMatchOutcome], list[str]]:
    from app_proc.data_root import get_online_data_root
    from evaluators.evaluate_zloto_monety import match_all_gold_purchase_rules

    warnings: list[str] = []
    if purchase_rules.empty:
        warnings.append("Brak reguł zakupu w zakładce zloto-monety-zakupy.")
        return [], warnings

    root = data_root if data_root is not None else get_online_data_root()
    catalog = assets_catalog if assets_catalog is not None else read_assets()
    outcomes = match_all_gold_purchase_rules(
        root, catalog, purchase_rules, warnings, valuation_date
    )
    return outcomes, warnings
