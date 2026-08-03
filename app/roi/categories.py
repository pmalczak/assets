# -*- coding: utf-8 -*-
from analyse_assets.data_model import AssetRw

CAPEX = "CAPEX"
REVENUES = "REVENUES"
OPEX = "OPEX"
DIVESTMENT = "DIVESTMENT"

ROI_CATEGORIES = (CAPEX, REVENUES, OPEX, DIVESTMENT)

# Stare nazwy z a_config / cache → kanoniczne.
CATEGORY_ALIASES = {
    "INVESTMENT": CAPEX,
    "INFLOW": REVENUES,
    "OUTFLOW": OPEX,
    "CLOSING": DIVESTMENT,
}

ASSET_RW_TO_ROI = {
    AssetRw.CAT_INVESTMENT: CAPEX,
    AssetRw.CAT_INFLOW: REVENUES,
    AssetRw.CAT_OUTFLOW: OPEX,
    AssetRw.CAT_CLOSING: DIVESTMENT,
}

ROI_TO_ASSET_RW = {value: key for key, value in ASSET_RW_TO_ROI.items()}


def normalize_roi_category(name: str) -> str:
    """Zwraca kanoniczną kategorię ROI (z aliasami starych nazw)."""
    key = str(name).strip()
    return CATEGORY_ALIASES.get(key, key)
