# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from importers.data_model_generic import GenericStructureClass


class AnalyseAssetsCatalogCls(GenericStructureClass):
    ASSET_ID = "asset_id"
    OUTPUT_FILE = "output_file"
    ORDER = "order"
    ENABLED = "enabled"
    PROPERTIES_ID = "properties_id"
    SOURCE = "source"

    def expected_columns(self) -> set:
        return {
            self.ASSET_ID,
            self.OUTPUT_FILE,
            self.ORDER,
            self.ENABLED,
            self.PROPERTIES_ID,
            self.SOURCE,
        }


class AnalyseAssetsRulesCls(GenericStructureClass):
    ASSET_ID = "asset_id"
    STEP_ID = "step_id"
    STEP_ORDER = "step_order"
    MAPPING = "mapping"
    CONDITION_GROUP = "condition_group"
    FIELD = "field"
    OPERATOR = "operator"
    VALUE = "value"
    UWAGI = "Uwagi"
    SOURCE = "source"

    def expected_columns(self) -> set:
        return {
            self.ASSET_ID,
            self.STEP_ID,
            self.STEP_ORDER,
            self.MAPPING,
            self.CONDITION_GROUP,
            self.FIELD,
            self.OPERATOR,
            self.VALUE,
            self.UWAGI,
            self.SOURCE,
        }


class AnalyseAssetsManualCls(GenericStructureClass):
    ASSET_ID = "asset_id"
    STEP_ORDER = "step_order"
    DATE = "date"
    AMOUNT = "amount"
    CATEGORY = "category"
    DESCRIPTION = "description"

    def expected_columns(self) -> set:
        return {
            self.ASSET_ID,
            self.STEP_ORDER,
            self.DATE,
            self.AMOUNT,
            self.CATEGORY,
            self.DESCRIPTION,
        }


AnalyseAssetsCatalog = AnalyseAssetsCatalogCls()
AnalyseAssetsRules = AnalyseAssetsRulesCls()
AnalyseAssetsManual = AnalyseAssetsManualCls()

CONFIG_FILE_NAME = "analyse_assets_config.xlsx"
CATALOG_SHEET = "assets"
RULES_SHEET = "rules"
MANUAL_SHEET = "manual"

DEFAULT_TRANSACTION_SOURCE = "mbank_pln"
MANUAL_TRANSACTION_SOURCE = "manual"

MAPPING_NAMES = {
    "initial_investment",
    "inflow_outflow",
    "investment_refund",
    "closing_investment",
    "inflow",
}

FIELD_NAMES = {
    "MBANK_TITLE",
    "MBANK_TRANSACTION_PARTY",
    "MBANK_ACCOUNT_NUMBER",
    "MBANK_AMOUNT",
    "MBANK_DESCRIPTION",
    "YEAR",
    "SOURCE",
}

OPERATOR_NAMES = {
    "contains",
    "contains_no_regex",
    "equals",
    "gte",
    "gt",
    "lte",
    "lt",
}

CATEGORY_NAMES = {
    "INVESTMENT",
    "INFLOW",
    "OUTFLOW",
    "CLOSING",
}
