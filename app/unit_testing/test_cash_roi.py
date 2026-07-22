import unittest
from datetime import date

import pandas as pd

from importers.assets.pool_id import MBANK_EUR
from analyse_assets.config_model import (
    ACCOUNT_ID_COLUMN,
    DEFAULT_POOL_ID,
    AnalyseAssetsCatalog,
    AnalyseAssetsManual,
    AnalyseAssetsRules,
)
from analyse_assets.data_model import AssetRw
from analyse_assets.select_asset import select_asset
from importers.assets.data_model import OperationDomain, PropertyValuations
from importers.mbank.data_model import MBankFile, MbankOperationType
from roi.allocate import allocate_catalog
from roi.categories import INVESTMENT
from roi.compute_roi import compute_roi
from roi.data_model import CashFlowEvent


def _tx(
    *,
    title: str,
    amount: float,
    description: str,
    source: str,
    account_id: str,
    party: str = "X",
    account_number: str = "123",
    tx_date: str = "2022-04-28",
) -> dict:
    return {
        AssetRw.TRANSACTION_DATE: tx_date,
        AssetRw.OPERATION_TYPE: description,
        AssetRw.TITLE: title,
        AssetRw.COUNTERPARTY: party,
        AssetRw.ACCOUNT_NUMBER: account_number,
        AssetRw.AMOUNT: amount,
        AssetRw.BALANCE: 0.0,
        AssetRw.ACCOUNT_ID: account_id,
        AssetRw.POOL_ID: source,
        MBankFile.EFFECTIVE_DATE: tx_date,
        MBankFile.DEBIT_ACCOUNT: account_id,
        ACCOUNT_ID_COLUMN: account_id,
    }


class CashRoiAllocationTests(unittest.TestCase):
    def test_source_scope_keeps_pln_and_eur_separate(self):
        pln = _tx(
            title="UMOWA PLN",
            amount=-100.0,
            description=MbankOperationType.PRZELEW_ZEWNETRZNY_WYCHODZACY,
            source=DEFAULT_POOL_ID,
            account_id="p_m_23_2330",
        )
        eur = _tx(
            title="DYWIDENDA",
            amount=100120.94,
            description=MbankOperationType.PRZELEW_SEPA_PRZYCHODZACY,
            source=MBANK_EUR,
            account_id="g_m_56_3217_eur",
        )
        pool = AssetRw.add_ymd_columns(pd.DataFrame([pln, eur]))
        catalog = pd.DataFrame(
            [
                {
                    AnalyseAssetsCatalog.ASSET_ID: "aquamarina",
                    AnalyseAssetsCatalog.OUTPUT_FILE: "mbank_aquamarina.xlsx",
                    "order": 1,
                    "enabled": True,
                    AnalyseAssetsCatalog.POOL_ID: DEFAULT_POOL_ID,
                },
                {
                    AnalyseAssetsCatalog.ASSET_ID: "cash",
                    AnalyseAssetsCatalog.OUTPUT_FILE: "mbank_cash.xlsx",
                    "order": 2,
                    "enabled": True,
                    AnalyseAssetsCatalog.POOL_ID: MBANK_EUR,
                },
            ]
        )
        rules = pd.DataFrame(
            [
                {
                    AnalyseAssetsRules.ASSET_ID: "aquamarina",
                    AnalyseAssetsRules.STEP_ID: "r0",
                    AnalyseAssetsRules.STEP_ORDER: 0,
                    AnalyseAssetsRules.MAPPING: "initial_investment",
                    AnalyseAssetsRules.CONDITION_GROUP: 1,
                    AnalyseAssetsRules.FIELD: "TITLE",
                    AnalyseAssetsRules.OPERATOR: "contains",
                    AnalyseAssetsRules.VALUE: "UMOWA PLN",
                    AnalyseAssetsRules.POOL_ID: "",
                },
                {
                    AnalyseAssetsRules.ASSET_ID: "cash",
                    AnalyseAssetsRules.STEP_ID: "r0",
                    AnalyseAssetsRules.STEP_ORDER: 0,
                    AnalyseAssetsRules.MAPPING: "initial_investment",
                    AnalyseAssetsRules.CONDITION_GROUP: 1,
                    AnalyseAssetsRules.FIELD: "ACCOUNT_ID",
                    AnalyseAssetsRules.OPERATOR: "equals",
                    AnalyseAssetsRules.VALUE: "g_m_56_3217_eur",
                    AnalyseAssetsRules.POOL_ID: "",
                },
                {
                    AnalyseAssetsRules.ASSET_ID: "cash",
                    AnalyseAssetsRules.STEP_ID: "r0",
                    AnalyseAssetsRules.STEP_ORDER: 0,
                    AnalyseAssetsRules.MAPPING: "initial_investment",
                    AnalyseAssetsRules.CONDITION_GROUP: 1,
                    AnalyseAssetsRules.FIELD: "TITLE",
                    AnalyseAssetsRules.OPERATOR: "contains",
                    AnalyseAssetsRules.VALUE: "DYWIDENDA",
                    AnalyseAssetsRules.POOL_ID: "",
                },
            ]
        )
        manual = pd.DataFrame(columns=list(AnalyseAssetsManual.expected_columns()))

        events_by_asset, unallocated = allocate_catalog(pool, catalog, rules, manual)

        self.assertEqual(len(events_by_asset["aquamarina"]), 1)
        self.assertEqual(events_by_asset["aquamarina"].iloc[0][CashFlowEvent.SOURCE], DEFAULT_POOL_ID)
        self.assertEqual(len(events_by_asset["cash"]), 1)
        self.assertEqual(events_by_asset["cash"].iloc[0][CashFlowEvent.SOURCE], MBANK_EUR)
        self.assertEqual(events_by_asset["cash"].iloc[0][CashFlowEvent.CATEGORY], INVESTMENT)
        self.assertLess(events_by_asset["cash"].iloc[0][CashFlowEvent.AMOUNT], 0)
        self.assertEqual(len(unallocated), 0)

    def test_mbank_source_account_selector(self):
        from analyse_assets.build_selector import build_step_selector

        row_ok = _tx(
            title="DYWIDENDA",
            amount=100.0,
            description=MbankOperationType.PRZELEW_SEPA_PRZYCHODZACY,
            source=MBANK_EUR,
            account_id="g_m_56_3217_eur",
        )
        row_other = _tx(
            title="DYWIDENDA",
            amount=100.0,
            description=MbankOperationType.PRZELEW_SEPA_PRZYCHODZACY,
            source=MBANK_EUR,
            account_id="p_m_63_3209_eur",
        )
        df = AssetRw.add_ymd_columns(pd.DataFrame([row_ok, row_other]))
        step_rules = pd.DataFrame(
            [
                {
                    AnalyseAssetsRules.CONDITION_GROUP: 1,
                    AnalyseAssetsRules.FIELD: "ACCOUNT_ID",
                    AnalyseAssetsRules.OPERATOR: "equals",
                    AnalyseAssetsRules.VALUE: "g_m_56_3217_eur",
                }
            ]
        )
        mask = build_step_selector(df, step_rules)
        self.assertTrue(mask.iloc[0])
        self.assertFalse(mask.iloc[1])

    def test_inbound_investment_amount_is_negated(self):
        df = AssetRw.add_ymd_columns(
            pd.DataFrame(
                [
                    _tx(
                        title="DYWIDENDA",
                        amount=100120.94,
                        description=MbankOperationType.PRZELEW_SEPA_PRZYCHODZACY,
                        source=MBANK_EUR,
                        account_id="g_m_56_3217_eur",
                    )
                ]
            )
        )
        selector = pd.Series([True], index=df.index)
        _remaining, selected = select_asset(
            df,
            selector,
            AssetRw.initial_investment_mapping,
        )
        self.assertEqual(selected.iloc[0][AssetRw.CAT], AssetRw.CAT_INVESTMENT)
        self.assertAlmostEqual(float(selected.iloc[0][AssetRw.AMOUNT]), -100120.94)

    def test_cash_roi_xirr_with_properties_valuation(self):
        events = pd.DataFrame(
            [
                {
                    CashFlowEvent.ASSET_ID: "cash",
                    CashFlowEvent.DATE: "2022-04-28",
                    CashFlowEvent.AMOUNT: -100120.94,
                    CashFlowEvent.CATEGORY: INVESTMENT,
                    CashFlowEvent.SOURCE: MBANK_EUR,
                    CashFlowEvent.DESCRIPTION: MbankOperationType.PRZELEW_SEPA_PRZYCHODZACY,
                    CashFlowEvent.TITLE: "DYWIDENDA",
                    CashFlowEvent.COUNTERPARTY: "GPM",
                    CashFlowEvent.ACCOUNT_NUMBER: "",
                }
            ]
        )
        props = pd.DataFrame(
            [
                {
                    PropertyValuations.ID: "cash",
                    PropertyValuations.DATE: "2026-01-01",
                    PropertyValuations.VALUE: 120000.0,
                    PropertyValuations.CURRENCY: "EUR",
                    PropertyValuations.SIZE: 1,
                    PropertyValuations.OPERATION: OperationDomain.EVALUATION,
                    PropertyValuations.UNIT_PRICE: 120000.0,
                }
            ]
        )
        summary = compute_roi("cash", events, props, date(2026, 1, 1), properties_id="cash")
        self.assertFalse(summary.is_sold)
        self.assertEqual(summary.terminal_unrealized, 120000.0)
        self.assertIsNotNone(summary.xirr)
        self.assertGreater(summary.xirr, 0.0)


class CashConfigValidationTests(unittest.TestCase):
    def test_mbank_eur_source_is_supported(self):
        import tempfile
        from pathlib import Path

        from analyse_assets.config_model import CATALOG_SHEET, MANUAL_SHEET, RULES_SHEET
        from analyse_assets.validate_config import validate_analyse_config

        catalog = pd.DataFrame(
            [
                {
                    AnalyseAssetsCatalog.ASSET_ID: "cash",
                    AnalyseAssetsCatalog.OUTPUT_FILE: "mbank_cash.xlsx",
                    AnalyseAssetsCatalog.ORDER: 1,
                    AnalyseAssetsCatalog.ENABLED: 1,
                    AnalyseAssetsCatalog.PROPERTIES_ID: "cash",
                    AnalyseAssetsCatalog.POOL_ID: MBANK_EUR,
                }
            ]
        )
        rules = pd.DataFrame(
            [
                {
                    AnalyseAssetsRules.ASSET_ID: "cash",
                    AnalyseAssetsRules.STEP_ID: "r0",
                    AnalyseAssetsRules.STEP_ORDER: 0,
                    AnalyseAssetsRules.MAPPING: "initial_investment",
                    AnalyseAssetsRules.CONDITION_GROUP: 1,
                    AnalyseAssetsRules.FIELD: "ACCOUNT_ID",
                    AnalyseAssetsRules.OPERATOR: "equals",
                    AnalyseAssetsRules.VALUE: "g_m_56_3217_eur",
                    AnalyseAssetsRules.UWAGI: "",
                    AnalyseAssetsRules.POOL_ID: "",
                }
            ]
        )
        manual = pd.DataFrame(columns=list(AnalyseAssetsManual.expected_columns()))
        path = Path(tempfile.mkdtemp()) / "analyse_assets_config.xlsx"
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            catalog.to_excel(writer, sheet_name=CATALOG_SHEET, index=False)
            rules.to_excel(writer, sheet_name=RULES_SHEET, index=False)
            manual.to_excel(writer, sheet_name=MANUAL_SHEET, index=False)

        report = validate_analyse_config(path)
        self.assertTrue(report.ok, "\n".join(i.format() for i in report.errors))


if __name__ == "__main__":
    unittest.main()
