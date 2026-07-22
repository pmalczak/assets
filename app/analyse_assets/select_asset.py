# -*- coding: utf-8 -*-
from __future__ import annotations

__author__ = "pmalczak@gmail.com"

import pandas as pd

from analyse_assets.config_model import AnalyseAssetsRules
from analyse_assets.data_model import AssetRw


def format_empty_selector_error(
    *,
    asset_id: str | None = None,
    step_rules: pd.DataFrame | None = None,
) -> str:
    """Komunikat diagnostyczny: asset_id oraz pary field/value z kroku reguł."""
    parts = ["Selektor nie zwrocil zadnych transakcji"]
    if asset_id is not None:
        parts.append(f"asset_id={asset_id!r}")
    if step_rules is not None and not step_rules.empty:
        field_col = AnalyseAssetsRules.FIELD
        value_col = AnalyseAssetsRules.VALUE
        if field_col in step_rules.columns and value_col in step_rules.columns:
            for _, row in step_rules.iterrows():
                parts.append(f"field={row[field_col]!r} value={row[value_col]!r}")
    return "; ".join(parts)


def select_asset(
    df: pd.DataFrame,
    selector,
    mapping: dict,
    *,
    asset_id: str | None = None,
    step_rules: pd.DataFrame | None = None,
) -> tuple:
    selected = df[selector].copy()
    remaining = df[~selector].copy()

    if selected.empty:
        raise ValueError(
            format_empty_selector_error(asset_id=asset_id, step_rules=step_rules)
        )

    cond = selected[AssetRw.OPERATION_TYPE].isin(mapping.keys())
    missing = selected.loc[~cond, AssetRw.OPERATION_TYPE].unique()

    if len(missing) > 0:
        raise ValueError(f"Brakujące wartości w mapowaniu: {missing}")

    selected[AssetRw.CAT] = selected[AssetRw.OPERATION_TYPE].replace(mapping)
    # INVESTMENT zawsze jako wypływ kapitału (ujemny), także przy zasileniu konta wpływem.
    investment = selected[AssetRw.CAT] == AssetRw.CAT_INVESTMENT
    if investment.any():
        amounts = pd.to_numeric(selected.loc[investment, AssetRw.AMOUNT], errors="coerce")
        selected.loc[investment, AssetRw.AMOUNT] = -amounts.abs()
    return remaining, selected
