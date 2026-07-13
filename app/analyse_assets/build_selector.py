# -*- coding: utf-8 -*-
from __future__ import annotations

__author__ = "pmalczak@gmail.com"

import pandas as pd

from analyse_assets.config_model import AnalyseAssetsRules, FIELD_NAMES, OPERATOR_NAMES
from analyse_assets.data_model import AssetRw


FIELD_MAP = {
    "MBANK_TITLE": AssetRw.MBANK_TITLE,
    "MBANK_TRANSACTION_PARTY": AssetRw.MBANK_TRANSACTION_PARTY,
    "MBANK_ACCOUNT_NUMBER": AssetRw.MBANK_ACCOUNT_NUMBER,
    "MBANK_AMOUNT": AssetRw.MBANK_AMOUNT,
    "YEAR": AssetRw.YEAR,
}

MAPPING_MAP = {
    "initial_investment": AssetRw.initial_investment_mapping,
    "inflow_outflow": AssetRw.inflow_outflow_mapping,
    "investment_refund": AssetRw.investment_refund_mapping,
    "closing_investment": AssetRw.closing_investment_mapping,
    "inflow": AssetRw.inflow_mapping,
}

CATEGORY_MAP = {
    "INVESTMENT": AssetRw.CAT_INVESTMENT,
    "INFLOW": AssetRw.CAT_INFLOW,
    "OUTFLOW": AssetRw.CAT_OUTFLOW,
    "CLOSING": AssetRw.CAT_CLOSING,
}


def is_blank_rule_value(value) -> bool:
    if pd.isna(value):
        return True
    text = str(value).strip()
    return not text or text.lower() == "nan"


def rule_cell_str(value) -> str | None:
    if is_blank_rule_value(value):
        return None
    return str(value).strip()


def get_mapping(name: str) -> dict:
    if name not in MAPPING_MAP:
        raise ValueError(f"Nieznane mapowanie: {name!r}")
    return MAPPING_MAP[name]


def apply_condition(df: pd.DataFrame, field: str, operator: str, value) -> pd.Series:
    if field not in FIELD_MAP:
        raise ValueError(f"Nieznane pole: {field!r}")
    if operator not in OPERATOR_NAMES:
        raise ValueError(f"Nieznany operator: {operator!r}")

    col = FIELD_MAP[field]
    series = df[col]
    if field == "MBANK_ACCOUNT_NUMBER":
        series = series.astype("string").str.replace(r"\.0$", "", regex=True)

    if operator == "contains":
        return series.astype("string").fillna("").str.contains(str(value), regex=True, na=False)
    if operator == "contains_no_regex":
        return series.astype("string").fillna("").str.contains(str(value), regex=False, na=False)
    if operator == "equals":
        if field == "YEAR":
            return series.astype("string") == str(value)
        if field == "MBANK_AMOUNT":
            return series == float(value)
        if field == "MBANK_ACCOUNT_NUMBER":
            return series.astype("string") == str(value).replace(".0", "")
        return series == value
    if operator == "gte":
        if field == "YEAR":
            return series.astype("string") >= str(value)
        return series >= float(value)
    if operator == "gt":
        if field == "MBANK_AMOUNT":
            return series > float(value)
        return series > value
    if operator == "lte":
        return series <= float(value)
    if operator == "lt":
        return series < float(value)

    raise ValueError(f"Operator nieobslugiwany: {operator!r}")


def build_step_selector(df: pd.DataFrame, step_rules: pd.DataFrame) -> pd.Series:
    if step_rules.empty:
        return pd.Series(False, index=df.index)

    or_masks: list[pd.Series] = []
    for _, group in step_rules.groupby(AnalyseAssetsRules.CONDITION_GROUP, sort=False):
        mask = pd.Series(True, index=df.index)
        has_condition = False
        for _, rule in group.iterrows():
            field = rule_cell_str(rule[AnalyseAssetsRules.FIELD])
            operator = rule_cell_str(rule[AnalyseAssetsRules.OPERATOR])
            if field is None or operator is None:
                continue
            has_condition = True
            mask &= apply_condition(
                df,
                field,
                operator,
                rule[AnalyseAssetsRules.VALUE],
            )
        if has_condition:
            or_masks.append(mask)

    if not or_masks:
        return pd.Series(False, index=df.index)

    result = or_masks[0]
    for mask in or_masks[1:]:
        result |= mask
    return result
