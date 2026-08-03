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
    rule_cell_str,
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


def _pool_id_from_field_equals(step_rules: pd.DataFrame) -> str | None:
    """Fallback: field=POOL_ID + operator=equals (gdy kolumna rules.pool_id pusta)."""
    if step_rules is None or step_rules.empty:
        return None
    needed = (
        AnalyseAssetsRules.FIELD,
        AnalyseAssetsRules.OPERATOR,
        AnalyseAssetsRules.VALUE,
    )
    if any(col not in step_rules.columns for col in needed):
        return None
    for _, row in step_rules.iterrows():
        field = rule_cell_str(row[AnalyseAssetsRules.FIELD])
        operator = rule_cell_str(row[AnalyseAssetsRules.OPERATOR])
        if field != "POOL_ID" or operator != "equals":
            continue
        if is_blank_rule_value(row[AnalyseAssetsRules.VALUE]):
            continue
        return str(row[AnalyseAssetsRules.VALUE]).strip()
    return None


def _effective_rule_pool_id(step_rules: pd.DataFrame, default_pool_id: str) -> str:
    """
    Pool kroku:
    1) niepusta kolumna rules.pool_id
    2) inaczej field=POOL_ID equals <value>
    3) inaczej assets.pool_id (default)
    """
    if AnalyseAssetsRules.POOL_ID in step_rules.columns:
        for value in step_rules[AnalyseAssetsRules.POOL_ID].tolist():
            if not is_blank_rule_value(value):
                return str(value).strip()
    from_field = _pool_id_from_field_equals(step_rules)
    if from_field is not None:
        return from_field
    return default_pool_id


def collect_pool_ids_from_rules(rules: pd.DataFrame, enabled_asset_ids: set[str]) -> list[str]:
    """Pool'e wskazane kolumną rules.pool_id lub field=POOL_ID equals."""
    if rules is None or rules.empty or not enabled_asset_ids:
        return []
    asset_rules = rules[
        rules[AnalyseAssetsRules.ASSET_ID].astype(str).str.strip().isin(enabled_asset_ids)
    ]
    if asset_rules.empty:
        return []

    ordered: list[str] = []
    if AnalyseAssetsRules.POOL_ID in asset_rules.columns:
        for value in asset_rules[AnalyseAssetsRules.POOL_ID].tolist():
            if is_blank_rule_value(value):
                continue
            pid = str(value).strip()
            if pid not in ordered:
                ordered.append(pid)

    needed = (
        AnalyseAssetsRules.FIELD,
        AnalyseAssetsRules.OPERATOR,
        AnalyseAssetsRules.VALUE,
    )
    if all(col in asset_rules.columns for col in needed):
        for _, row in asset_rules.iterrows():
            field = rule_cell_str(row[AnalyseAssetsRules.FIELD])
            operator = rule_cell_str(row[AnalyseAssetsRules.OPERATOR])
            if field != "POOL_ID" or operator != "equals":
                continue
            if is_blank_rule_value(row[AnalyseAssetsRules.VALUE]):
                continue
            pid = str(row[AnalyseAssetsRules.VALUE]).strip()
            if pid not in ordered:
                ordered.append(pid)
    return ordered


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

    event_parts: list[pd.DataFrame] = []
    remaining = df.copy()
    for step_kind, _, payload in steps:
        if step_kind == "manual":
            part = _build_manual_part(payload)
            event_parts.append(
                asset_rw_to_cashflow_events(part, asset_id, source=MANUAL_TRANSACTION_SOURCE)
            )
            continue

        _step_id, step_rules = payload
        mapping_name = str(step_rules[AnalyseAssetsRules.MAPPING].iloc[0])
        # rules.pool_id niepuste → pool kroku; puste → assets.pool_id (katalog).
        step_pool_id = _effective_rule_pool_id(step_rules, pool_id)
        step_remaining, other_pools = _split_pool_by_pool_id(remaining, step_pool_id)
        selector = build_step_selector(step_remaining, step_rules)
        step_remaining, selected = select_asset(
            step_remaining,
            selector,
            get_mapping(mapping_name),
            asset_id=asset_id,
            step_rules=step_rules,
        )
        remaining = pd.concat([step_remaining, other_pools], ignore_index=True)
        event_parts.append(
            asset_rw_to_cashflow_events(selected, asset_id, source=step_pool_id)
        )

    if not event_parts:
        return remaining, _empty_events(asset_id)

    events = pd.concat(event_parts, ignore_index=True)
    CashFlowEvent.check_structure(events)
    return remaining, events


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
        from roi.categories import normalize_roi_category

        category = CATEGORY_MAP[normalize_roi_category(str(row[AnalyseAssetsManual.CATEGORY]))]
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
