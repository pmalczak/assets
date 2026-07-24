# -*- coding: utf-8 -*-
from pathlib import Path

import pandas as pd

from analyse_assets.build_selector import is_blank_rule_value
from analyse_assets.config_model import (
    CONFIG_FILE_NAME,
    CATALOG_SHEET,
    DEFAULT_POOL_ID,
    MANUAL_SHEET,
    RULES_SHEET,
    AnalyseAssetsCatalog,
    AnalyseAssetsManual,
    AnalyseAssetsRules,
)
from app_proc.data_root import get_online_data_root


def _drop_incomplete_rules(rules: pd.DataFrame) -> pd.DataFrame:
    field = rules[AnalyseAssetsRules.FIELD]
    operator = rules[AnalyseAssetsRules.OPERATOR]
    complete = ~field.map(is_blank_rule_value) & ~operator.map(is_blank_rule_value)
    return rules.loc[complete].reset_index(drop=True)


def _normalize_rules_columns(rules: pd.DataFrame) -> pd.DataFrame:
    rules = rules.copy()
    if AnalyseAssetsRules.UWAGI not in rules.columns:
        rules[AnalyseAssetsRules.UWAGI] = ""
    else:
        rules[AnalyseAssetsRules.UWAGI] = rules[AnalyseAssetsRules.UWAGI].fillna("").astype(str)

    if AnalyseAssetsRules.POOL_ID in rules.columns:
        rules[AnalyseAssetsRules.POOL_ID] = (
            rules[AnalyseAssetsRules.POOL_ID].fillna("").astype(str).str.strip()
        )
        rules.loc[
            rules[AnalyseAssetsRules.POOL_ID].str.lower().isin({"", "nan"}),
            AnalyseAssetsRules.POOL_ID,
        ] = ""
    return rules


def _normalize_catalog_pool_id(catalog: pd.DataFrame) -> pd.DataFrame:
    catalog = catalog.copy()
    if AnalyseAssetsCatalog.POOL_ID in catalog.columns:
        catalog[AnalyseAssetsCatalog.POOL_ID] = (
            catalog[AnalyseAssetsCatalog.POOL_ID]
            .fillna(DEFAULT_POOL_ID)
            .astype(str)
            .str.strip()
        )
        blank = catalog[AnalyseAssetsCatalog.POOL_ID].str.lower().isin({"", "nan"})
        catalog.loc[blank, AnalyseAssetsCatalog.POOL_ID] = DEFAULT_POOL_ID
    return catalog


def get_config_file(config_path: Path | None = None) -> Path:
    if config_path is not None:
        return config_path
    return get_online_data_root() / CONFIG_FILE_NAME


def read_analyse_config(config_path: Path | None = None) -> dict[str, pd.DataFrame]:
    source = get_config_file(config_path)
    assert source.is_file(), source

    catalog = pd.read_excel(source, sheet_name=CATALOG_SHEET)
    rules = _normalize_rules_columns(
        _drop_incomplete_rules(pd.read_excel(source, sheet_name=RULES_SHEET))
    )
    manual = pd.read_excel(source, sheet_name=MANUAL_SHEET)

    catalog = _normalize_catalog_pool_id(catalog)

    AnalyseAssetsCatalog.check_structure(catalog)
    AnalyseAssetsRules.check_structure(rules)
    AnalyseAssetsManual.check_structure(manual)

    return {
        "catalog": catalog,
        "rules": rules,
        "manual": manual,
    }
