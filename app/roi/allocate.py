# -*- coding: utf-8 -*-
from __future__ import annotations

import pandas as pd

from analyse_assets.account_tx import AccountTx
from analyse_assets.build_selector import (
    CATEGORY_MAP,
    build_step_selector,
    get_mapping,
    is_blank_rule_value,
    normalize_whitespace,
)
from analyse_assets.config_model import (
    DEFAULT_POOL_ID,
    MANUAL_TRANSACTION_SOURCE,
    AnalyseAssetsCatalog,
    AnalyseAssetsManual,
    AnalyseAssetsRules,
)
from analyse_assets.data_model import AssetRw
from analyse_assets.select_asset import select_asset
from roi.categories import ASSET_RW_TO_ROI
from roi.data_model import CashFlowEvent


def _text_column(raw: pd.DataFrame, column: str) -> pd.Series:
    if column not in raw.columns:
        return pd.Series([""] * len(raw), index=raw.index, dtype="string")
    return raw[column].astype("string").fillna("").map(normalize_whitespace)


def _catalog_default_pool_id(asset_row: pd.Series) -> str:
    if AnalyseAssetsCatalog.POOL_ID not in asset_row.index:
        return DEFAULT_POOL_ID
    value = asset_row[AnalyseAssetsCatalog.POOL_ID]
    if is_blank_rule_value(value):
        return DEFAULT_POOL_ID
    return str(value).strip()


def _effective_rule_pool_id(step_rules: pd.DataFrame, default_pool_id: str) -> str:
    if AnalyseAssetsRules.POOL_ID not in step_rules.columns:
        return default_pool_id
    for value in step_rules[AnalyseAssetsRules.POOL_ID].tolist():
        if not is_blank_rule_value(value):
            return str(value).strip()
    return default_pool_id


def _split_pool_by_pool_id(
    df: pd.DataFrame,
    pool_id: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Wydziel wiersze danego pool_id; reszta poola zostaje nietknięta przy alokacji reguł."""
    if df.empty:
        empty = df.copy()
        return empty, empty
    col = AccountTx.POOL_ID
    if col not in df.columns:
        return df.copy(), df.iloc[0:0].copy()

    mask = df[col].astype("string").fillna("") == pool_id
    return df.loc[mask].copy(), df.loc[~mask].copy()


def allocate_asset_from_mbank_pool(
    df: pd.DataFrame,
    asset_id: str,
    rules: pd.DataFrame,
    manual: pd.DataFrame,
    *,
    default_source: str | None = None,
    default_pool_id: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    pool_id = default_pool_id or default_source or DEFAULT_POOL_ID
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

    scoped_pool, other_pools = _split_pool_by_pool_id(df, pool_id)

    event_parts: list[pd.DataFrame] = []
    remaining = scoped_pool
    for step_kind, _, payload in steps:
        if step_kind == "manual":
            part = _build_manual_part(payload)
            event_parts.append(
                asset_rw_to_cashflow_events(part, asset_id, source=MANUAL_TRANSACTION_SOURCE)
            )
            continue

        _step_id, step_rules = payload
        mapping_name = str(step_rules[AnalyseAssetsRules.MAPPING].iloc[0])
        effective_pool_id = _effective_rule_pool_id(step_rules, pool_id)
        selector = build_step_selector(remaining, step_rules)
        remaining, selected = select_asset(remaining, selector, get_mapping(mapping_name))
        event_parts.append(
            asset_rw_to_cashflow_events(selected, asset_id, source=effective_pool_id)
        )

    merged_remaining = pd.concat([remaining, other_pools], ignore_index=True)

    if not event_parts:
        return df, _empty_events(asset_id)

    events = pd.concat(event_parts, ignore_index=True)
    CashFlowEvent.check_structure(events)
    return merged_remaining, events


def asset_rw_to_cashflow_events(
    raw: pd.DataFrame,
    asset_id: str,
    *,
    source: str,
) -> pd.DataFrame:
    if raw.empty:
        return _empty_events(asset_id)

    pool_col = AccountTx.POOL_ID
    if pool_col in raw.columns:
        source_values = (
            raw[pool_col]
            .astype("string")
            .fillna(source)
            .map(lambda value: source if is_blank_rule_value(value) else str(value).strip())
        )
    else:
        source_values = source

    dates = pd.to_datetime(raw[AssetRw.TRANSACTION_DATE], errors="coerce")
    result = pd.DataFrame(
        {
            CashFlowEvent.ASSET_ID: asset_id,
            # Jednolity string YYYY-MM-DD — inaczej parquet pada na mieszance Timestamp/str.
            CashFlowEvent.DATE: dates.dt.strftime("%Y-%m-%d"),
            CashFlowEvent.AMOUNT: pd.to_numeric(raw[AssetRw.AMOUNT], errors="coerce"),
            CashFlowEvent.CATEGORY: raw[AssetRw.CAT].map(ASSET_RW_TO_ROI),
            CashFlowEvent.SOURCE: source_values,
            CashFlowEvent.DESCRIPTION: _text_column(raw, AssetRw.OPERATION_TYPE),
            CashFlowEvent.TITLE: _text_column(raw, AssetRw.TITLE),
            CashFlowEvent.COUNTERPARTY: _text_column(raw, AssetRw.COUNTERPARTY),
            CashFlowEvent.ACCOUNT_NUMBER: _text_column(raw, AssetRw.ACCOUNT_NUMBER),
        }
    )
    result = result.dropna(subset=[CashFlowEvent.AMOUNT, CashFlowEvent.CATEGORY, CashFlowEvent.DATE])
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
        default_pool_id = _catalog_default_pool_id(asset_row)
        pool, events = allocate_asset_from_mbank_pool(
            pool,
            asset_id,
            rules,
            manual,
            default_pool_id=default_pool_id,
        )
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


# Kompatybilność
_split_pool_by_source = _split_pool_by_pool_id
_catalog_default_source = _catalog_default_pool_id
_effective_rule_source = _effective_rule_pool_id
