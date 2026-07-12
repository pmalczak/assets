# -*- coding: utf-8 -*-
from analyse_assets.data_model import AssetRw

INVESTMENT = "INVESTMENT"
INFLOW = "INFLOW"
OUTFLOW = "OUTFLOW"
CLOSING = "CLOSING"

ROI_CATEGORIES = (INVESTMENT, INFLOW, OUTFLOW, CLOSING)

ASSET_RW_TO_ROI = {
    AssetRw.CAT_INVESTMENT: INVESTMENT,
    AssetRw.CAT_INFLOW: INFLOW,
    AssetRw.CAT_OUTFLOW: OUTFLOW,
    AssetRw.CAT_CLOSING: CLOSING,
}

ROI_TO_ASSET_RW = {value: key for key, value in ASSET_RW_TO_ROI.items()}
