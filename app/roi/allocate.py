# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

import pandas as pd

from analyse_assets.build_selector import CATEGORY_MAP, build_step_selector, get_mapping
from analyse_assets.config_model import AnalyseAssetsManual, AnalyseAssetsRules
from analyse_assets.data_model import AssetRw
from analyse_assets.select_asset import select_asset
from importers.mbank.data_model import MBankFile
from roi.categories import ASSET_RW_TO_ROI
from roi.data_model import CashFlowEvent


def normalize_whitespace(value) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    return " ".join(text.split())


def _text_column(raw: pd.DataFrame, column: str) -> pd.Series:
    if column not in raw.columns:
        return pd.Series([""] * len(raw), index=raw.index, dtype="string")
    return raw[column].astype("string").fillna("").map(normalize_whitespace)


def allocate_asset_from_mbank_pool(
    df: pd.DataFrame,
    asset_id: str,
    rules: pd.DataFrame,
    manual: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    asset_rules = rules[rules[AnalyseAssetsRules.ASSET_ID] == asset_id].copy()
    asset_manual = manual[manual[AnalyseAssetsManual.ASSET_ID] == asset_id].copy()

    steps: list[tuple[str, int, object]] = []

    if not asset_rules.empty:
        for (step_id, step_order), step_rules in asset_rules.groupby(
            [AnalyseAssetsRules.STEP_ID, AnalyseAssetsRules.STEP_ORDER],
            sort=False,
        ):
            steps.append(("rule", int(step_order), (str(step_id), step_rules)))

    if not asset_manual.empty:
        for step_order, step_rows in asset_manual.groupby(AnalyseAssetsManual.STEP_ORDER, sort=True):
            steps.append(("manual", int(step_order), step_rows))

    steps.sort(key=lambda item: item[1])

    parts: list[pd.DataFrame] = []
    remaining = df
    for step_kind, _, payload in steps:
        if step_kind == "manual":
            parts.append(_build_manual_part(payload))
            continue

        _step_id, step_rules = payload
        mapping_name = str(step_rules[AnalyseAssetsRules.MAPPING].iloc[0])
        selector = build_step_selector(remaining, step_rules)
        remaining, selected = select_asset(remaining, selector, get_mapping(mapping_name))
        parts.append(selected)

    if not parts:
        return df, _empty_events(asset_id)

    raw = pd.concat(parts, ignore_index=True)
    events = asset_rw_to_cashflow_events(raw, asset_id, source="mbank")
    return remaining, events


def asset_rw_to_cashflow_events(
    raw: pd.DataFrame,
    asset_id: str,
    *,
    source: str,
) -> pd.DataFrame:
    if raw.empty:
        return _empty_events(asset_id)

    result = pd.DataFrame(
        {
            CashFlowEvent.ASSET_ID: asset_id,
            CashFlowEvent.DATE: raw[AssetRw.MBANK_TRANSACTION_DATE],
            CashFlowEvent.AMOUNT: pd.to_numeric(raw[AssetRw.MBANK_AMOUNT], errors="coerce"),
            CashFlowEvent.CATEGORY: raw[AssetRw.CAT].map(ASSET_RW_TO_ROI),
            CashFlowEvent.SOURCE: source,
            CashFlowEvent.DESCRIPTION: _text_column(raw, AssetRw.MBANK_DESCRIPTION),
            CashFlowEvent.TITLE: _text_column(raw, MBankFile.MBANK_TITLE),
            CashFlowEvent.COUNTERPARTY: _text_column(raw, MBankFile.MBANK_TRANSACTION_PARTY),
            CashFlowEvent.ACCOUNT_NUMBER: _text_column(raw, MBankFile.MBANK_ACCOUNT_NUMBER),
        }
    )
    result = result.dropna(subset=[CashFlowEvent.AMOUNT, CashFlowEvent.CATEGORY])
    CashFlowEvent.check_structure(result)
    return result.reset_index(drop=True)


def allocate_catalog(
    df: pd.DataFrame,
    catalog: pd.DataFrame,
    rules: pd.DataFrame,
    manual: pd.DataFrame,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    pool = df.copy()
    events_by_asset: dict[str, pd.DataFrame] = {}

    enabled = catalog[catalog["enabled"].astype(bool)].sort_values("order")
    for _, asset_row in enabled.iterrows():
        asset_id = str(asset_row["asset_id"])
        pool, events = allocate_asset_from_mbank_pool(pool, asset_id, rules, manual)
        events_by_asset[asset_id] = events

    return events_by_asset, pool


def _build_manual_part(step_rows: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in step_rows.iterrows():
        category = CATEGORY_MAP[str(row[AnalyseAssetsManual.CATEGORY])]
        rows.append(
            (
                pd.Timestamp(row[AnalyseAssetsManual.DATE]).strftime("%Y-%m-%d"),
                float(row[AnalyseAssetsManual.AMOUNT]),
                category,
                str(row[AnalyseAssetsManual.DESCRIPTION]),
            )
        )
    return AssetRw.create(rows)


def _empty_events(asset_id: str) -> pd.DataFrame:
    return pd.DataFrame(columns=list(CashFlowEvent.COLUMN_ORDER))
