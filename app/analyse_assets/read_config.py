# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from analyse_assets.config_model import (
    CONFIG_FILE_NAME,
    CATALOG_SHEET,
    MANUAL_SHEET,
    RULES_SHEET,
    AnalyseAssetsCatalog,
    AnalyseAssetsManual,
    AnalyseAssetsRules,
)


def get_config_file(config_path: Path | None = None) -> Path:
    if config_path is not None:
        return config_path
    return Path(__file__).parent / CONFIG_FILE_NAME


def read_analyse_config(config_path: Path | None = None) -> dict[str, pd.DataFrame]:
    source = get_config_file(config_path)
    assert source.is_file(), source

    catalog = pd.read_excel(source, sheet_name=CATALOG_SHEET)
    rules = pd.read_excel(source, sheet_name=RULES_SHEET)
    manual = pd.read_excel(source, sheet_name=MANUAL_SHEET)

    AnalyseAssetsCatalog.check_structure(catalog)
    AnalyseAssetsRules.check_structure(rules)
    AnalyseAssetsManual.check_structure(manual)

    return {
        "catalog": catalog,
        "rules": rules,
        "manual": manual,
    }
