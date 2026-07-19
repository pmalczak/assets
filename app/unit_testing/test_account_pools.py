import unittest

import pandas as pd

from analyse_assets.account_tx import (
    AccountTx,
    mbank_statement_to_account_tx,
    revolut_statement_to_account_tx,
)
from analyse_assets.build_selector import FIELD_MAP, apply_condition, build_step_selector
from analyse_assets.config_model import AnalyseAssetsRules
from analyse_assets.consolidate_and_drop_internal_transfers import (
    consolidate_account_tx_drop_internal_transfers,
)
from importers.assets.data_model import AssetsFile, KindDomain, TypeDomain
from importers.assets.pool_id import (
    MBANK_EUR,
    MBANK_PLN,
    POOL_ID_COLUMN,
    REVOLUT_PLN,
    assign_pool_id,
    resolve_pool_id,
)
from importers.mbank.data_model import MBankFile, MbankOperationType
from importers.revolut.account_data_model import RevolutAccountFile
from app_proc.export_product_excel import unallocated_excel_filename
from roi.roi_products import roi_summary_resource


class AssignPoolIdTests(unittest.TestCase):
    def test_resolve_pool_id_mapping(self):
        self.assertEqual(resolve_pool_id("mbank.PM", "PLN"), MBANK_PLN)
        self.assertEqual(resolve_pool_id("mbank.GM", "EUR"), MBANK_EUR)
        self.assertEqual(resolve_pool_id("revolut.PM", "PLN"), REVOLUT_PLN)
        self.assertIsNone(resolve_pool_id("mbank.PM", "USD"))
        self.assertIsNone(resolve_pool_id("assets.cash", "PLN"))

    def test_assign_pool_id_for_ror(self):
        assets = pd.DataFrame(
            [
                {
                    AssetsFile.ID: "g_m_23",
                    AssetsFile.TYPE: TypeDomain.CURRENT_ACCOUNT,
                    AssetsFile.KIND: KindDomain.MBANK + ".GM",
                    AssetsFile.CURRENCY: "PLN",
                },
                {
                    AssetsFile.ID: "prop1",
                    AssetsFile.TYPE: TypeDomain.PROPERTY,
                    AssetsFile.KIND: "assets.properties",
                    AssetsFile.CURRENCY: "PLN",
                },
            ]
        )
        result = assign_pool_id(assets)
        self.assertEqual(result.iloc[0][POOL_ID_COLUMN], MBANK_PLN)
        self.assertEqual(result.iloc[1][POOL_ID_COLUMN], "")

    def test_assign_pool_id_raises_for_unmapped_ror(self):
        assets = pd.DataFrame(
            [
                {
                    AssetsFile.ID: "bad_ror",
                    AssetsFile.TYPE: TypeDomain.CURRENT_ACCOUNT,
                    AssetsFile.KIND: "assets.cash",
                    AssetsFile.CURRENCY: "PLN",
                }
            ]
        )
        with self.assertRaises(ValueError) as ctx:
            assign_pool_id(assets)
        self.assertIn("bad_ror", str(ctx.exception))


class AccountTxAdapterTests(unittest.TestCase):
    def test_mbank_adapter_columns(self):
        raw = pd.DataFrame(
            [
                {
                    MBankFile.MBANK_TRANSACTION_DATE: "2020-01-01",
                    MBankFile.MBANK_DESCRIPTION: MbankOperationType.PRZELEW_ZEWNETRZNY_WYCHODZACY,
                    MBankFile.MBANK_TITLE: "UMOWA",
                    MBankFile.MBANK_TRANSACTION_PARTY: "X",
                    MBankFile.MBANK_ACCOUNT_NUMBER: "123",
                    MBankFile.MBANK_AMOUNT: -10.0,
                    MBankFile.MBANK_OUTSTANDING_BALANCE: 0.0,
                }
            ]
        )
        tx = mbank_statement_to_account_tx(raw, account_id="acc1", pool_id=MBANK_PLN)
        self.assertEqual(tx.iloc[0][AccountTx.OPERATION_TYPE], MbankOperationType.PRZELEW_ZEWNETRZNY_WYCHODZACY)
        self.assertEqual(tx.iloc[0][AccountTx.TITLE], "UMOWA")
        self.assertEqual(tx.iloc[0][AccountTx.ACCOUNT_ID], "acc1")
        self.assertEqual(tx.iloc[0][AccountTx.POOL_ID], MBANK_PLN)

    def test_revolut_adapter_columns(self):
        raw = pd.DataFrame(
            [
                {
                    RevolutAccountFile.DATE: "2020-01-01",
                    RevolutAccountFile.KIND: "Transfer",
                    RevolutAccountFile.DESCRIPTION: "To savings",
                    RevolutAccountFile.PRODUCT: "Current",
                    RevolutAccountFile.AMOUNT: -5.0,
                    RevolutAccountFile.BALANCE: 10.0,
                }
            ]
        )
        tx = revolut_statement_to_account_tx(raw, account_id="re1", pool_id=REVOLUT_PLN)
        self.assertEqual(tx.iloc[0][AccountTx.OPERATION_TYPE], "Transfer")
        self.assertEqual(tx.iloc[0][AccountTx.TITLE], "To savings")
        self.assertEqual(list(tx.columns), list(AccountTx.COLUMN_ORDER))


class ConsolidateAccountTxTests(unittest.TestCase):
    def test_mbank_internal_transfer_pair_dropped(self):
        a = pd.DataFrame(
            [
                {
                    AccountTx.TRANSACTION_DATE: "2020-01-01",
                    AccountTx.OPERATION_TYPE: MbankOperationType.PRZELEW_WEWNETRZNY_WYCHODZACY,
                    AccountTx.TITLE: "wewn",
                    AccountTx.COUNTERPARTY: "",
                    AccountTx.ACCOUNT_NUMBER: "acc_b",
                    AccountTx.AMOUNT: -100.0,
                    AccountTx.BALANCE: 0.0,
                    AccountTx.ACCOUNT_ID: "acc_a",
                    AccountTx.POOL_ID: MBANK_PLN,
                }
            ]
        )
        b = pd.DataFrame(
            [
                {
                    AccountTx.TRANSACTION_DATE: "2020-01-01",
                    AccountTx.OPERATION_TYPE: MbankOperationType.PRZELEW_WEWNETRZNY_PRZYCHODZACY,
                    AccountTx.TITLE: "wewn",
                    AccountTx.COUNTERPARTY: "",
                    AccountTx.ACCOUNT_NUMBER: "acc_a",
                    AccountTx.AMOUNT: 100.0,
                    AccountTx.BALANCE: 0.0,
                    AccountTx.ACCOUNT_ID: "acc_b",
                    AccountTx.POOL_ID: MBANK_PLN,
                }
            ]
        )
        cleaned, _report, meta = consolidate_account_tx_drop_internal_transfers(
            [a, b], bank="mbank"
        )
        self.assertEqual(meta["pairs_removed"], 1)
        self.assertEqual(len(cleaned), 0)

    def test_one_sided_internal_transfer_does_not_raise(self):
        """Tylko OUT (bez IN) — wcześniej KeyError: _rank przy merge."""
        only_out = pd.DataFrame(
            [
                {
                    AccountTx.TRANSACTION_DATE: "2020-01-01",
                    AccountTx.OPERATION_TYPE: MbankOperationType.PRZELEW_WEWNETRZNY_WYCHODZACY,
                    AccountTx.TITLE: "wewn",
                    AccountTx.COUNTERPARTY: "",
                    AccountTx.ACCOUNT_NUMBER: "acc_b",
                    AccountTx.AMOUNT: -50.0,
                    AccountTx.BALANCE: 0.0,
                    AccountTx.ACCOUNT_ID: "acc_a",
                    AccountTx.POOL_ID: MBANK_PLN,
                }
            ]
        )
        cleaned, _report, meta = consolidate_account_tx_drop_internal_transfers(
            [only_out], bank="mbank"
        )
        self.assertEqual(meta["pairs_removed"], 0)
        self.assertEqual(len(cleaned), 1)


class SelectorFieldAliasTests(unittest.TestCase):
    def test_semantic_and_mbank_aliases_map_same_columns(self):
        self.assertEqual(FIELD_MAP["TITLE"], AccountTx.TITLE)
        self.assertEqual(FIELD_MAP["MBANK_TITLE"], AccountTx.TITLE)
        self.assertEqual(FIELD_MAP["OPERATION_TYPE"], AccountTx.OPERATION_TYPE)
        self.assertEqual(FIELD_MAP["MBANK_DESCRIPTION"], AccountTx.OPERATION_TYPE)
        self.assertEqual(FIELD_MAP["ACCOUNT_ID"], AccountTx.ACCOUNT_ID)
        self.assertEqual(FIELD_MAP["MBANK_SOURCE_ACCOUNT"], AccountTx.ACCOUNT_ID)
        self.assertEqual(FIELD_MAP["POOL_ID"], AccountTx.POOL_ID)
        self.assertEqual(FIELD_MAP["SOURCE"], AccountTx.POOL_ID)

    def test_operation_type_selector(self):
        df = pd.DataFrame(
            [
                {
                    AccountTx.OPERATION_TYPE: MbankOperationType.PRZELEW_SEPA_PRZYCHODZACY,
                    AccountTx.TITLE: "X",
                },
                {
                    AccountTx.OPERATION_TYPE: MbankOperationType.ZAKUP_PRZY_UZYCIU_KARTY,
                    AccountTx.TITLE: "Y",
                },
            ]
        )
        mask = apply_condition(
            df, "OPERATION_TYPE", "equals", MbankOperationType.PRZELEW_SEPA_PRZYCHODZACY
        )
        self.assertTrue(mask.iloc[0])
        self.assertFalse(mask.iloc[1])

        step_rules = pd.DataFrame(
            [
                {
                    AnalyseAssetsRules.CONDITION_GROUP: 1,
                    AnalyseAssetsRules.FIELD: "MBANK_DESCRIPTION",
                    AnalyseAssetsRules.OPERATOR: "equals",
                    AnalyseAssetsRules.VALUE: MbankOperationType.PRZELEW_SEPA_PRZYCHODZACY,
                }
            ]
        )
        alias_mask = build_step_selector(df, step_rules)
        self.assertTrue(alias_mask.iloc[0])
        self.assertFalse(alias_mask.iloc[1])


class RoiProductPathTests(unittest.TestCase):
    def test_unallocated_excel_filename_includes_pool_id(self):
        self.assertEqual(
            unallocated_excel_filename(MBANK_EUR),
            "unallocated_mbank_eur.xlsx",
        )

    def test_roi_summary_resource_includes_date(self):
        from datetime import date

        self.assertEqual(
            roi_summary_resource(date(2026, 7, 17)),
            "10 roi/2026-07-17/_roi_summary.parquet",
        )


if __name__ == "__main__":
    unittest.main()
