import tempfile
import unittest
from pathlib import Path

import pandas as pd

from analyse_assets.config_model import (
    CATALOG_SHEET,
    DEFAULT_TRANSACTION_SOURCE,
    MANUAL_SHEET,
    RULES_SHEET,
    AnalyseAssetsCatalog,
    AnalyseAssetsManual,
    AnalyseAssetsRules,
)
from analyse_assets.validate_config import validate_analyse_config
from importers.mbank.data_model import MbankOperationType


class ValidateAnalyseConfigTests(unittest.TestCase):
    def _write_config(self, catalog: pd.DataFrame, rules: pd.DataFrame, manual: pd.DataFrame) -> Path:
        path = Path(tempfile.mkdtemp()) / "analyse_assets_config.xlsx"
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            catalog.to_excel(writer, sheet_name=CATALOG_SHEET, index=False)
            rules.to_excel(writer, sheet_name=RULES_SHEET, index=False)
            manual.to_excel(writer, sheet_name=MANUAL_SHEET, index=False)
        return path

    def _minimal_catalog(self, **overrides) -> pd.DataFrame:
        row = {
            AnalyseAssetsCatalog.ASSET_ID: "aquamarina",
            AnalyseAssetsCatalog.OUTPUT_FILE: "mbank_aquamarina.xlsx",
            AnalyseAssetsCatalog.ORDER: 1,
            AnalyseAssetsCatalog.ENABLED: 1,
            AnalyseAssetsCatalog.PROPERTIES_ID: "aquamarina",
            AnalyseAssetsCatalog.SOURCE: DEFAULT_TRANSACTION_SOURCE,
        }
        row.update(overrides)
        return pd.DataFrame([row])

    def _minimal_rule(self, **overrides) -> pd.DataFrame:
        row = {
            AnalyseAssetsRules.ASSET_ID: "aquamarina",
            AnalyseAssetsRules.STEP_ID: "r0",
            AnalyseAssetsRules.STEP_ORDER: 0,
            AnalyseAssetsRules.MAPPING: "initial_investment",
            AnalyseAssetsRules.CONDITION_GROUP: 1,
            AnalyseAssetsRules.FIELD: "MBANK_TITLE",
            AnalyseAssetsRules.OPERATOR: "contains",
            AnalyseAssetsRules.VALUE: "ZAKUP",
            AnalyseAssetsRules.UWAGI: "",
            AnalyseAssetsRules.SOURCE: "",
        }
        row.update(overrides)
        return pd.DataFrame([row])

    def _empty_manual(self) -> pd.DataFrame:
        return pd.DataFrame(columns=list(AnalyseAssetsManual.expected_columns()))

    def test_valid_minimal_config_ok(self):
        path = self._write_config(
            self._minimal_catalog(),
            self._minimal_rule(),
            self._empty_manual(),
        )
        report = validate_analyse_config(path)
        self.assertTrue(report.ok, format_issues := "\n".join(i.format() for i in report.errors))
        self.assertEqual(format_issues, "")

    def test_unknown_mapping_is_error(self):
        path = self._write_config(
            self._minimal_catalog(),
            self._minimal_rule(**{AnalyseAssetsRules.MAPPING: "not_a_mapping"}),
            self._empty_manual(),
        )
        report = validate_analyse_config(path)
        codes = {i.code for i in report.errors}
        self.assertIn("unknown_mapping", codes)

    def test_unknown_field_is_error(self):
        path = self._write_config(
            self._minimal_catalog(),
            self._minimal_rule(**{AnalyseAssetsRules.FIELD: "REVOLUT_DESCRIPTION"}),
            self._empty_manual(),
        )
        report = validate_analyse_config(path)
        codes = {i.code for i in report.errors}
        self.assertIn("unknown_field", codes)

    def test_unsupported_catalog_source_is_error(self):
        path = self._write_config(
            self._minimal_catalog(**{AnalyseAssetsCatalog.SOURCE: "revolut"}),
            self._minimal_rule(),
            self._empty_manual(),
        )
        report = validate_analyse_config(path)
        codes = {i.code for i in report.errors}
        self.assertIn("unsupported_source", codes)

    def test_rule_asset_must_exist_in_catalog(self):
        path = self._write_config(
            self._minimal_catalog(),
            self._minimal_rule(**{AnalyseAssetsRules.ASSET_ID: "missing"}),
            self._empty_manual(),
        )
        report = validate_analyse_config(path)
        codes = {i.code for i in report.errors}
        self.assertIn("unknown_asset_id", codes)

    def test_manual_amount_sign_for_investment(self):
        manual = pd.DataFrame(
            [
                {
                    AnalyseAssetsManual.ASSET_ID: "aquamarina",
                    AnalyseAssetsManual.STEP_ORDER: 0,
                    AnalyseAssetsManual.DATE: "2020-01-01",
                    AnalyseAssetsManual.AMOUNT: 100.0,
                    AnalyseAssetsManual.CATEGORY: "INVESTMENT",
                    AnalyseAssetsManual.DESCRIPTION: "bad sign",
                }
            ]
        )
        path = self._write_config(
            self._minimal_catalog(),
            self._minimal_rule(),
            manual,
        )
        report = validate_analyse_config(path)
        codes = {i.code for i in report.errors}
        self.assertIn("amount_sign", codes)

    def test_operator_field_mismatch(self):
        path = self._write_config(
            self._minimal_catalog(),
            self._minimal_rule(
                **{
                    AnalyseAssetsRules.FIELD: "MBANK_TITLE",
                    AnalyseAssetsRules.OPERATOR: "gte",
                    AnalyseAssetsRules.VALUE: "2020",
                }
            ),
            self._empty_manual(),
        )
        report = validate_analyse_config(path)
        codes = {i.code for i in report.errors}
        self.assertIn("operator_field_mismatch", codes)

    def test_inconsistent_mapping_in_step(self):
        rules = pd.DataFrame(
            [
                {
                    AnalyseAssetsRules.ASSET_ID: "aquamarina",
                    AnalyseAssetsRules.STEP_ID: "r0",
                    AnalyseAssetsRules.STEP_ORDER: 0,
                    AnalyseAssetsRules.MAPPING: "initial_investment",
                    AnalyseAssetsRules.CONDITION_GROUP: 1,
                    AnalyseAssetsRules.FIELD: "MBANK_TITLE",
                    AnalyseAssetsRules.OPERATOR: "contains",
                    AnalyseAssetsRules.VALUE: "A",
                    AnalyseAssetsRules.UWAGI: "",
                    AnalyseAssetsRules.SOURCE: "",
                },
                {
                    AnalyseAssetsRules.ASSET_ID: "aquamarina",
                    AnalyseAssetsRules.STEP_ID: "r0",
                    AnalyseAssetsRules.STEP_ORDER: 0,
                    AnalyseAssetsRules.MAPPING: "inflow_outflow",
                    AnalyseAssetsRules.CONDITION_GROUP: 1,
                    AnalyseAssetsRules.FIELD: "MBANK_TITLE",
                    AnalyseAssetsRules.OPERATOR: "contains",
                    AnalyseAssetsRules.VALUE: "B",
                    AnalyseAssetsRules.UWAGI: "",
                    AnalyseAssetsRules.SOURCE: "",
                },
            ]
        )
        path = self._write_config(self._minimal_catalog(), rules, self._empty_manual())
        report = validate_analyse_config(path)
        codes = {i.code for i in report.errors}
        self.assertIn("inconsistent_mapping", codes)

    def test_pool_selector_reports_missing_mapping_coverage(self):
        from analyse_assets.config_model import AnalyseAssetsCatalog as Cat
        from analyse_assets.data_model import AssetRw

        pool = pd.DataFrame(
            [
                {
                    AssetRw.MBANK_TRANSACTION_DATE: "2020-01-01",
                    AssetRw.MBANK_DESCRIPTION: MbankOperationType.BLIK_ZAKUP_NFC,
                    AssetRw.MBANK_TITLE: "ZAKUP TEST",
                    AssetRw.MBANK_TRANSACTION_PARTY: "X",
                    AssetRw.MBANK_ACCOUNT_NUMBER: "123",
                    AssetRw.MBANK_AMOUNT: -10.0,
                    Cat.SOURCE: DEFAULT_TRANSACTION_SOURCE,
                }
            ]
        )
        path = self._write_config(
            self._minimal_catalog(),
            self._minimal_rule(
                **{
                    AnalyseAssetsRules.MAPPING: "initial_investment",
                    AnalyseAssetsRules.FIELD: "MBANK_TITLE",
                    AnalyseAssetsRules.OPERATOR: "contains",
                    AnalyseAssetsRules.VALUE: "ZAKUP",
                }
            ),
            self._empty_manual(),
        )
        report = validate_analyse_config(path, pool=pool, check_pool=True)
        codes = {i.code for i in report.errors}
        self.assertIn("selector_runtime", codes)


if __name__ == "__main__":
    unittest.main()
