# -*- coding: utf-8 -*-
from pathlib import Path

import pandas as pd

from analyse_assets.build_selector import is_blank_rule_value
from analyse_assets.config_model import (
    CONFIG_FILE_NAME,
    CATALOG_SHEET,
    DEFAULT_TRANSACTION_SOURCE,
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

    if AnalyseAssetsRules.SOURCE not in rules.columns:
        rules[AnalyseAssetsRules.SOURCE] = ""
    else:
        rules[AnalyseAssetsRules.SOURCE] = (
            rules[AnalyseAssetsRules.SOURCE].fillna("").astype(str).str.strip()
        )
        rules.loc[
            rules[AnalyseAssetsRules.SOURCE].str.lower().isin({"", "nan"}),
            AnalyseAssetsRules.SOURCE,
        ] = ""
    return rules


def _normalize_catalog_source(catalog: pd.DataFrame) -> pd.DataFrame:
    catalog = catalog.copy()
    if AnalyseAssetsCatalog.SOURCE not in catalog.columns:
        catalog[AnalyseAssetsCatalog.SOURCE] = DEFAULT_TRANSACTION_SOURCE
    else:
        catalog[AnalyseAssetsCatalog.SOURCE] = (
            catalog[AnalyseAssetsCatalog.SOURCE]
            .fillna(DEFAULT_TRANSACTION_SOURCE)
            .astype(str)
            .str.strip()
        )
        blank = catalog[AnalyseAssetsCatalog.SOURCE].str.lower().isin({"", "nan"})
        catalog.loc[blank, AnalyseAssetsCatalog.SOURCE] = DEFAULT_TRANSACTION_SOURCE
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

    if AnalyseAssetsCatalog.PROPERTIES_ID not in catalog.columns:
        catalog[AnalyseAssetsCatalog.PROPERTIES_ID] = catalog[AnalyseAssetsCatalog.ASSET_ID]
    else:
        catalog[AnalyseAssetsCatalog.PROPERTIES_ID] = (
            catalog[AnalyseAssetsCatalog.PROPERTIES_ID]
            .fillna(catalog[AnalyseAssetsCatalog.ASSET_ID])
            .astype(str)
        )
    catalog = _normalize_catalog_source(catalog)

    AnalyseAssetsCatalog.check_structure(catalog)
    AnalyseAssetsRules.check_structure(rules)
    AnalyseAssetsManual.check_structure(manual)

    return {
        "catalog": catalog,
        "rules": rules,
        "manual": manual,
    }
