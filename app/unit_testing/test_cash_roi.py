import unittest
from datetime import date
from unittest.mock import patch

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
from importers.assets.data_model import (
    AssetsDef,
    AssetsFile,
    GroupDomain,
    KindDomain,
    OperationDomain,
    PropertyValuations,
    TypeDomain,
)
from importers.mbank.data_model import MBankFile, MbankOperationType
from roi.allocate import allocate_catalog
from roi.categories import CAPEX
from roi.compute_roi import compute_roi
from roi.data_model import CashFlowEvent
from roi.terminal_value import resolve_terminal_value


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
        self.assertEqual(events_by_asset["cash"].iloc[0][CashFlowEvent.CATEGORY], CAPEX)
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
                    CashFlowEvent.CATEGORY: CAPEX,
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
        empty_cfg = {"catalog": pd.DataFrame(), "rules": pd.DataFrame(), "manual": pd.DataFrame()}
        with patch("roi.terminal_value.read_analyse_config", return_value=empty_cfg):
            summary = compute_roi("cash", events, props, date(2026, 1, 1))
        self.assertFalse(summary.is_sold)
        self.assertEqual(summary.terminal_unrealized, 120000.0)
        self.assertIsNotNone(summary.xirr)
        self.assertGreater(summary.xirr, 0.0)

    def test_cash_terminal_ignores_future_properties_valuation(self):
        events = pd.DataFrame(columns=list(CashFlowEvent.COLUMN_ORDER))
        props = pd.DataFrame(
            [
                {
                    PropertyValuations.ID: "cash",
                    PropertyValuations.DATE: "2025-11-15",
                    PropertyValuations.VALUE: 100000.0,
                    PropertyValuations.CURRENCY: "EUR",
                    PropertyValuations.SIZE: 1,
                    PropertyValuations.OPERATION: OperationDomain.EVALUATION,
                    PropertyValuations.UNIT_PRICE: 100000.0,
                },
                {
                    PropertyValuations.ID: "cash",
                    PropertyValuations.DATE: "2026-10-01",
                    PropertyValuations.VALUE: 999999.0,
                    PropertyValuations.CURRENCY: "EUR",
                    PropertyValuations.SIZE: 1,
                    PropertyValuations.OPERATION: OperationDomain.EVALUATION,
                    PropertyValuations.UNIT_PRICE: 999999.0,
                },
            ]
        )
        empty_cfg = {"catalog": pd.DataFrame(), "rules": pd.DataFrame(), "manual": pd.DataFrame()}
        with patch("roi.terminal_value.read_analyse_config", return_value=empty_cfg):
            _, unrealized, warnings = resolve_terminal_value(
                "cash",
                events,
                props,
                date(2026, 7, 22),
            )
        self.assertEqual(warnings, [])
        self.assertAlmostEqual(unrealized, 100000.0)

    def test_cash_snapshot_from_properties_wyceny(self):
        from evaluators.evaluate_assets_file import evaluate_assets_file

        props = pd.DataFrame(
            [
                {
                    PropertyValuations.ID: "cash",
                    PropertyValuations.DATE: "2025-11-15",
                    PropertyValuations.VALUE: 100000.0,
                    PropertyValuations.CURRENCY: "EUR",
                    PropertyValuations.SIZE: 1,
                    PropertyValuations.OPERATION: OperationDomain.EVALUATION,
                    PropertyValuations.UNIT_PRICE: 100000.0,
                },
                {
                    PropertyValuations.ID: "garaz",
                    PropertyValuations.DATE: "2025-01-01",
                    PropertyValuations.VALUE: 35000.0,
                    PropertyValuations.CURRENCY: "PLN",
                    PropertyValuations.SIZE: 18.9,
                    PropertyValuations.OPERATION: OperationDomain.EVALUATION,
                    PropertyValuations.UNIT_PRICE: 1851.85,
                },
            ]
        )
        assets_row = pd.Series(
            {
                AssetsFile.ID: "cash",
                AssetsFile.TYPE: TypeDomain.CASH,
                AssetsFile.GROUP: GroupDomain.CASH,
                AssetsFile.DESCR: "cash",
                AssetsFile.KIND: f"{KindDomain.ASSETS}.cash",
                AssetsFile.CURRENCY: "EUR",
                AssetsFile.NOTES: "",
            }
        )
        with patch(
            "evaluators.evaluate_assets_file.read_property_valuations",
            return_value=props,
        ), patch(
            "evaluators.evaluate_assets_file.read_analyse_config",
            return_value={
                "manual": pd.DataFrame(columns=list(AnalyseAssetsManual.expected_columns())),
                "catalog": pd.DataFrame(columns=list(AnalyseAssetsCatalog.expected_columns())),
            },
        ):
            result = evaluate_assets_file("assets.cash", assets_row, date(2026, 7, 22))

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0][AssetsDef.ID], "cash")
        self.assertAlmostEqual(float(result.iloc[0][AssetsDef.VALUE]), 100000.0)
        self.assertEqual(str(result.iloc[0][AssetsDef.CURRENCY]).upper(), "EUR")

    def test_properties_wyceny_excludes_cash_owned_ids(self):
        from evaluators.evaluate_assets_file import evaluate_assets_file

        props = pd.DataFrame(
            [
                {
                    PropertyValuations.ID: "cash",
                    PropertyValuations.DATE: "2025-11-15",
                    PropertyValuations.VALUE: 100000.0,
                    PropertyValuations.CURRENCY: "EUR",
                    PropertyValuations.SIZE: 1,
                    PropertyValuations.OPERATION: OperationDomain.EVALUATION,
                    PropertyValuations.UNIT_PRICE: 100000.0,
                },
                {
                    PropertyValuations.ID: "rocky-iv",
                    PropertyValuations.DATE: "2025-11-15",
                    PropertyValuations.VALUE: 50000.0,
                    PropertyValuations.CURRENCY: "EUR",
                    PropertyValuations.SIZE: 1,
                    PropertyValuations.OPERATION: OperationDomain.EVALUATION,
                    PropertyValuations.UNIT_PRICE: 50000.0,
                },
                {
                    PropertyValuations.ID: "garaz",
                    PropertyValuations.DATE: "2025-01-01",
                    PropertyValuations.VALUE: 35000.0,
                    PropertyValuations.CURRENCY: "PLN",
                    PropertyValuations.SIZE: 18.9,
                    PropertyValuations.OPERATION: OperationDomain.EVALUATION,
                    PropertyValuations.UNIT_PRICE: 1851.85,
                },
            ]
        )
        assets_catalog = pd.DataFrame(
            [
                {
                    AssetsFile.ID: "cash",
                    AssetsFile.TYPE: TypeDomain.CASH,
                    AssetsFile.GROUP: GroupDomain.CASH,
                    AssetsFile.DESCR: "cash",
                    AssetsFile.KIND: f"{KindDomain.ASSETS}.cash",
                    AssetsFile.CURRENCY: "EUR",
                    AssetsFile.NOTES: "",
                },
                {
                    AssetsFile.ID: "rocky-iv",
                    AssetsFile.TYPE: TypeDomain.EQUITIES,
                    AssetsFile.GROUP: GroupDomain.INVESTMENT,
                    AssetsFile.DESCR: "rocky",
                    AssetsFile.KIND: f"{KindDomain.ASSETS}.cash",
                    AssetsFile.CURRENCY: "EUR",
                    AssetsFile.NOTES: "",
                },
                {
                    AssetsFile.ID: "nieruchomosci",
                    AssetsFile.TYPE: TypeDomain.PROPERTY,
                    AssetsFile.GROUP: GroupDomain.PROPERTY,
                    AssetsFile.DESCR: "props",
                    AssetsFile.KIND: f"{KindDomain.ASSETS}.properties-wyceny",
                    AssetsFile.CURRENCY: "PLN",
                    AssetsFile.NOTES: "",
                },
            ]
        )
        assets_row = assets_catalog.iloc[2]
        with patch(
            "evaluators.evaluate_assets_file.read_property_valuations",
            return_value=props,
        ), patch(
            "evaluators.evaluate_assets_file.read_assets",
            return_value=assets_catalog,
        ), patch(
            "evaluators.evaluate_assets_file.read_analyse_config",
            return_value={
                "manual": pd.DataFrame(columns=list(AnalyseAssetsManual.expected_columns())),
                "catalog": pd.DataFrame(columns=list(AnalyseAssetsCatalog.expected_columns())),
            },
        ), patch(
            "evaluators.evaluate_assets_file.load_roi_aware_close_dates",
            return_value={},
        ):
            result = evaluate_assets_file(
                "assets.properties-wyceny",
                assets_row,
                date(2026, 7, 22),
            )

        self.assertIsNotNone(result)
        ids = set(result[AssetsDef.ID].astype(str))
        self.assertEqual(ids, {"garaz"})
        self.assertNotIn("cash", ids)
        self.assertNotIn("rocky-iv", ids)


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
        path = Path(tempfile.mkdtemp()) / "a_config.xlsx"
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            catalog.to_excel(writer, sheet_name=CATALOG_SHEET, index=False)
            rules.to_excel(writer, sheet_name=RULES_SHEET, index=False)
            manual.to_excel(writer, sheet_name=MANUAL_SHEET, index=False)
            from importers.assets.data_model import INSTRUMENTS_SHEET
            from importers.assets.instruments import empty_instruments_table
            empty_instruments_table().to_excel(writer, sheet_name=INSTRUMENTS_SHEET, index=False)

        report = validate_analyse_config(path)
        self.assertTrue(report.ok, "\n".join(i.format() for i in report.errors))


if __name__ == "__main__":
    unittest.main()
