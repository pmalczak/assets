# -*- coding: utf-8 -*-
import unittest
from datetime import date
from unittest.mock import patch

import pandas as pd

from analyse_assets.config_model import (
    ACCOUNT_ID_COLUMN,
    DEFAULT_POOL_ID,
    AnalyseAssetsCatalog,
    AnalyseAssetsManual,
    AnalyseAssetsRules,
)
from analyse_assets.data_model import AssetRw
from importers.assets.data_model import Inventory, UnitPriceEvaluation
from importers.assets.pool_id import REVOLUT_PLN
from importers.mbank.data_model import MBankFile, MbankOperationType
from importers.revolut.account_data_model import RevolutOperationType
from roi.allocate import allocate_catalog
from roi.categories import CAPEX
from roi.data_model import CashFlowEvent
from roi.gold_terminal import (
    GOLD_COINS_ROI_ASSET_ID,
    GoldInventoryJoinError,
    holdings_from_capex_and_inventory,
    mark_to_market,
    resolve_gold_terminal_unrealized,
)
from roi.terminal_value import resolve_terminal_value


def _tx(
    *,
    title: str,
    amount: float,
    description: str,
    account_id: str = "p_m_34_9142",
    tx_date: str = "2024-03-15",
    pool_id: str = DEFAULT_POOL_ID,
) -> dict:
    return {
        AssetRw.TRANSACTION_DATE: tx_date,
        AssetRw.OPERATION_TYPE: description,
        AssetRw.TITLE: title,
        AssetRw.COUNTERPARTY: "MENNICA",
        AssetRw.ACCOUNT_NUMBER: "123",
        AssetRw.AMOUNT: amount,
        AssetRw.BALANCE: 0.0,
        AssetRw.ACCOUNT_ID: account_id,
        AssetRw.POOL_ID: pool_id,
        MBankFile.EFFECTIVE_DATE: tx_date,
        MBankFile.DEBIT_ACCOUNT: account_id,
        ACCOUNT_ID_COLUMN: account_id,
    }


def _capex_event(
    *,
    tx_date: str,
    amount: float = -15000.0,
    source: str = DEFAULT_POOL_ID,
    title: str = "GRUPA GOLDENMARK",
    counterparty: str = "GOLDENMARK SP Z O O",
) -> dict:
    return {
        CashFlowEvent.ASSET_ID: GOLD_COINS_ROI_ASSET_ID,
        CashFlowEvent.DATE: tx_date,
        CashFlowEvent.AMOUNT: amount,
        CashFlowEvent.CATEGORY: CAPEX,
        CashFlowEvent.SOURCE: source,
        CashFlowEvent.DESCRIPTION: "CAPEX",
        CashFlowEvent.TITLE: title,
        CashFlowEvent.COUNTERPARTY: counterparty,
        CashFlowEvent.ACCOUNT_NUMBER: "",
    }


def _inventory_row(
    *,
    tx_date: str,
    instrument: str,
    quantity: float = 1.0,
    weight: str = "1oz",
) -> dict:
    return {
        Inventory.DATE: tx_date,
        Inventory.INSTRUMENT: instrument,
        Inventory.WEIGHT: weight,
        Inventory.QUANTITY: quantity,
        Inventory.NOTES: "",
    }


class GoldTerminalMtmTests(unittest.TestCase):
    def test_mark_to_market_two_coins(self):
        holdings = {"Krugerrand 1oz": 2.0, "Maple Leaf 1oz": 1.0}
        prices = pd.DataFrame(
            [
                {
                    UnitPriceEvaluation.DATE: "2025-06-01",
                    UnitPriceEvaluation.INSTRUMENT: "Krugerrand 1oz",
                    UnitPriceEvaluation.UNIT_PRICE: 10000.0,
                    UnitPriceEvaluation.NOTES: "",
                },
                {
                    UnitPriceEvaluation.DATE: "2025-06-01",
                    UnitPriceEvaluation.INSTRUMENT: "Maple Leaf 1oz",
                    UnitPriceEvaluation.UNIT_PRICE: 9500.0,
                    UnitPriceEvaluation.NOTES: "",
                },
                {
                    UnitPriceEvaluation.DATE: "2026-01-01",
                    UnitPriceEvaluation.INSTRUMENT: "Krugerrand 1oz",
                    UnitPriceEvaluation.UNIT_PRICE: 11000.0,
                    UnitPriceEvaluation.NOTES: "nowsza",
                },
            ]
        )
        value, warnings = mark_to_market(holdings, prices, date(2026, 7, 1))
        self.assertEqual(warnings, [])
        self.assertAlmostEqual(value, 31500.0)

    def test_missing_unit_price_warns_and_skips_coin(self):
        holdings = {"Krugerrand 1oz": 1.0, "Unknown": 3.0}
        prices = pd.DataFrame(
            [
                {
                    UnitPriceEvaluation.DATE: "2026-01-01",
                    UnitPriceEvaluation.INSTRUMENT: "Krugerrand 1oz",
                    UnitPriceEvaluation.UNIT_PRICE: 10000.0,
                    UnitPriceEvaluation.NOTES: "",
                },
            ]
        )
        value, warnings = mark_to_market(holdings, prices, date(2026, 7, 1))
        self.assertAlmostEqual(value, 10000.0)
        self.assertEqual(len(warnings), 1)
        self.assertIn("Unknown", warnings[0])

    def test_holdings_join_capex_and_inventory_by_date(self):
        cashflows = pd.DataFrame(
            [
                _capex_event(tx_date="2024-03-15", title="MENNICA A"),
                _capex_event(tx_date="2024-05-10", title="MENNICA B", amount=-9000.0),
            ]
        )
        inventory = pd.DataFrame(
            [
                _inventory_row(tx_date="2024-03-15", instrument="Krugerrand 1oz", quantity=2),
                _inventory_row(tx_date="2024-05-10", instrument="Maple Leaf 1oz", quantity=1),
            ]
        )
        holdings, warnings = holdings_from_capex_and_inventory(
            cashflows, inventory, date(2026, 7, 1)
        )
        self.assertEqual(warnings, [])
        self.assertEqual(holdings, {"Krugerrand 1oz": 2.0, "Maple Leaf 1oz": 1.0})

    def test_holdings_missing_inventory_raises_with_capex_context(self):
        cashflows = pd.DataFrame(
            [
                _capex_event(
                    tx_date="2026-05-06",
                    source="mbank_pln",
                    title="GRUPA GOLDENMARK...",
                    counterparty="GOLDENMARK",
                ),
            ]
        )
        inventory = pd.DataFrame(columns=list(Inventory.expected_columns()))
        with self.assertRaises(GoldInventoryJoinError) as ctx:
            holdings_from_capex_and_inventory(cashflows, inventory, date(2026, 7, 1))
        msg = str(ctx.exception)
        self.assertTrue(
            msg.startswith(
                "Dla transakcji date=2026-05-06 source='mbank_pln' "
                "title='GRUPA GOLDENMARK...' counterparty='GOLDENMARK' "
                "Brak jest wpisu w tabeli 'inventory' dla CAPEX"
            ),
            msg,
        )
        self.assertIn("no_inventory_row", msg)

    def test_holdings_ambiguous_inventory_date_raises(self):
        cashflows = pd.DataFrame([_capex_event(tx_date="2024-03-15")])
        inventory = pd.DataFrame(
            [
                _inventory_row(tx_date="2024-03-15", instrument="Krugerrand 1oz", quantity=1),
                _inventory_row(tx_date="2024-03-15", instrument="Maple Leaf 1oz", quantity=1),
            ]
        )
        with self.assertRaises(GoldInventoryJoinError) as ctx:
            holdings_from_capex_and_inventory(cashflows, inventory, date(2026, 7, 1))
        msg = str(ctx.exception)
        self.assertIn("ambiguous_inventory_date", msg)
        self.assertIn("date=2024-03-15", msg)

    def test_resolve_gold_terminal_from_capex_join(self):
        cashflows = pd.DataFrame(
            [
                _capex_event(tx_date="2024-03-15"),
                _capex_event(tx_date="2024-05-10", amount=-9000.0),
            ]
        )
        inventory = pd.DataFrame(
            [
                _inventory_row(tx_date="2024-03-15", instrument="Krugerrand 1oz", quantity=2),
                _inventory_row(tx_date="2024-05-10", instrument="Maple Leaf 1oz", quantity=1),
            ]
        )
        prices = pd.DataFrame(
            [
                {
                    UnitPriceEvaluation.DATE: "2026-01-01",
                    UnitPriceEvaluation.INSTRUMENT: "Krugerrand 1oz",
                    UnitPriceEvaluation.UNIT_PRICE: 12000.0,
                    UnitPriceEvaluation.NOTES: "",
                },
                {
                    UnitPriceEvaluation.DATE: "2026-01-01",
                    UnitPriceEvaluation.INSTRUMENT: "Maple Leaf 1oz",
                    UnitPriceEvaluation.UNIT_PRICE: 11000.0,
                    UnitPriceEvaluation.NOTES: "",
                },
            ]
        )
        value, warnings = resolve_gold_terminal_unrealized(
            date(2026, 7, 1),
            cashflows=cashflows,
            inventory=inventory,
            unit_prices=prices,
        )
        self.assertEqual(warnings, [])
        self.assertAlmostEqual(value, 35000.0)

    def test_resolve_terminal_value_gold_branch_passes_cashflows(self):
        cashflows = pd.DataFrame([_capex_event(tx_date="2024-03-15")])
        with patch(
            "roi.terminal_value.resolve_gold_terminal_unrealized",
            return_value=(35000.0, []),
        ) as mocked, patch(
            "roi.terminal_value.is_asset_sold",
            return_value=False,
        ):
            realized, unrealized, warnings = resolve_terminal_value(
                GOLD_COINS_ROI_ASSET_ID,
                cashflows,
                None,
                date(2026, 7, 1),
            )
        self.assertEqual(realized, 0.0)
        self.assertAlmostEqual(unrealized, 35000.0)
        self.assertEqual(warnings, [])
        kwargs = mocked.call_args.kwargs
        passed = kwargs["cashflows"]
        self.assertEqual(len(passed), 1)
        self.assertAlmostEqual(float(passed.iloc[0][CashFlowEvent.AMOUNT]), -15000.0)
        self.assertEqual(passed.iloc[0][CashFlowEvent.CATEGORY], CAPEX)


class GoldCapexAllocationTests(unittest.TestCase):
    def test_capex_from_title_and_amount_rule(self):
        pool = AssetRw.add_ymd_columns(
            pd.DataFrame(
                [
                    _tx(
                        title="ZAKUP MENNICA KRUGERRAND",
                        amount=-15000.0,
                        description=MbankOperationType.PRZELEW_ZEWNETRZNY_WYCHODZACY,
                    ),
                    _tx(
                        title="INNY PRZELEW",
                        amount=-100.0,
                        description=MbankOperationType.PRZELEW_ZEWNETRZNY_WYCHODZACY,
                        tx_date="2024-03-16",
                    ),
                ]
            )
        )
        catalog = pd.DataFrame(
            [
                {
                    AnalyseAssetsCatalog.ASSET_ID: GOLD_COINS_ROI_ASSET_ID,
                    AnalyseAssetsCatalog.OUTPUT_FILE: "mbank_zloto_monety.xlsx",
                    "order": 1,
                    "enabled": True,
                    AnalyseAssetsCatalog.POOL_ID: DEFAULT_POOL_ID,
                },
            ]
        )
        rules = pd.DataFrame(
            [
                {
                    AnalyseAssetsRules.ASSET_ID: GOLD_COINS_ROI_ASSET_ID,
                    AnalyseAssetsRules.STEP_ID: "gold_buy",
                    AnalyseAssetsRules.STEP_ORDER: 0,
                    AnalyseAssetsRules.MAPPING: "initial_investment",
                    AnalyseAssetsRules.CONDITION_GROUP: 1,
                    AnalyseAssetsRules.FIELD: "TITLE",
                    AnalyseAssetsRules.OPERATOR: "contains",
                    AnalyseAssetsRules.VALUE: "MENNICA",
                    AnalyseAssetsRules.POOL_ID: "",
                },
                {
                    AnalyseAssetsRules.ASSET_ID: GOLD_COINS_ROI_ASSET_ID,
                    AnalyseAssetsRules.STEP_ID: "gold_buy",
                    AnalyseAssetsRules.STEP_ORDER: 0,
                    AnalyseAssetsRules.MAPPING: "initial_investment",
                    AnalyseAssetsRules.CONDITION_GROUP: 1,
                    AnalyseAssetsRules.FIELD: "AMOUNT",
                    AnalyseAssetsRules.OPERATOR: "equals",
                    AnalyseAssetsRules.VALUE: "-15000",
                    AnalyseAssetsRules.POOL_ID: "",
                },
            ]
        )
        manual = pd.DataFrame(columns=list(AnalyseAssetsManual.expected_columns()))

        events_by_asset, unallocated = allocate_catalog(pool, catalog, rules, manual)

        self.assertEqual(len(events_by_asset[GOLD_COINS_ROI_ASSET_ID]), 1)
        event = events_by_asset[GOLD_COINS_ROI_ASSET_ID].iloc[0]
        self.assertEqual(event[CashFlowEvent.CATEGORY], CAPEX)
        self.assertAlmostEqual(float(event[CashFlowEvent.AMOUNT]), -15000.0)
        self.assertEqual(len(unallocated), 1)

    def test_capex_from_two_pools_via_field_pool_id_equals(self):
        """Gdy kolumna rules.pool_id pusta: field=POOL_ID equals ustawia pool kroku."""
        pool = AssetRw.add_ymd_columns(
            pd.DataFrame(
                [
                    _tx(
                        title="Grupa Goldenmark",
                        amount=-35438.0,
                        description=RevolutOperationType.CARD_PAYMENT,
                        account_id="p_re_pln",
                        tx_date="2026-04-21",
                        pool_id=REVOLUT_PLN,
                    ),
                    _tx(
                        title="INNY",
                        amount=-10.0,
                        description=MbankOperationType.PRZELEW_ZEWNETRZNY_WYCHODZACY,
                        pool_id=DEFAULT_POOL_ID,
                    ),
                ]
            )
        )
        catalog = pd.DataFrame(
            [
                {
                    AnalyseAssetsCatalog.ASSET_ID: GOLD_COINS_ROI_ASSET_ID,
                    AnalyseAssetsCatalog.OUTPUT_FILE: "a_zloto.xlsx",
                    "order": 1,
                    "enabled": True,
                    AnalyseAssetsCatalog.POOL_ID: DEFAULT_POOL_ID,
                },
            ]
        )
        rules = pd.DataFrame(
            [
                {
                    AnalyseAssetsRules.ASSET_ID: GOLD_COINS_ROI_ASSET_ID,
                    AnalyseAssetsRules.STEP_ID: "revolut_buy",
                    AnalyseAssetsRules.STEP_ORDER: 0,
                    AnalyseAssetsRules.MAPPING: "initial_investment",
                    AnalyseAssetsRules.CONDITION_GROUP: 1,
                    AnalyseAssetsRules.FIELD: "POOL_ID",
                    AnalyseAssetsRules.OPERATOR: "equals",
                    AnalyseAssetsRules.VALUE: REVOLUT_PLN,
                    AnalyseAssetsRules.POOL_ID: "",
                },
                {
                    AnalyseAssetsRules.ASSET_ID: GOLD_COINS_ROI_ASSET_ID,
                    AnalyseAssetsRules.STEP_ID: "revolut_buy",
                    AnalyseAssetsRules.STEP_ORDER: 0,
                    AnalyseAssetsRules.MAPPING: "initial_investment",
                    AnalyseAssetsRules.CONDITION_GROUP: 1,
                    AnalyseAssetsRules.FIELD: "TITLE",
                    AnalyseAssetsRules.OPERATOR: "contains",
                    AnalyseAssetsRules.VALUE: "Grupa Goldenmark",
                    AnalyseAssetsRules.POOL_ID: "",
                },
            ]
        )
        manual = pd.DataFrame(columns=list(AnalyseAssetsManual.expected_columns()))
        events_by_asset, unallocated = allocate_catalog(pool, catalog, rules, manual)
        events = events_by_asset[GOLD_COINS_ROI_ASSET_ID]
        self.assertEqual(len(events), 1)
        self.assertEqual(events.iloc[0][CashFlowEvent.SOURCE], REVOLUT_PLN)
        self.assertAlmostEqual(float(events.iloc[0][CashFlowEvent.AMOUNT]), -35438.0)
        self.assertEqual(len(unallocated), 1)

    def test_capex_from_two_pools_via_rules_pool_id(self):
        """rules.pool_id wybiera pool kroku; puste â†’ assets.pool_id."""
        pool = AssetRw.add_ymd_columns(
            pd.DataFrame(
                [
                    _tx(
                        title="GRUPA GOLDENMARK   /WROCLAW",
                        amount=-34278.0,
                        description=MbankOperationType.ZAKUP_PRZY_UZYCIU_KARTY,
                        account_id="p_m_23_2330",
                        tx_date="2026-05-06",
                        pool_id=DEFAULT_POOL_ID,
                    ),
                    _tx(
                        title="Grupa Goldenmark",
                        amount=-35438.0,
                        description=RevolutOperationType.CARD_PAYMENT,
                        account_id="p_re_pln",
                        tx_date="2026-04-21",
                        pool_id=REVOLUT_PLN,
                    ),
                    _tx(
                        title="INNY",
                        amount=-10.0,
                        description=MbankOperationType.PRZELEW_ZEWNETRZNY_WYCHODZACY,
                        tx_date="2026-05-07",
                        pool_id=DEFAULT_POOL_ID,
                    ),
                ]
            )
        )
        catalog = pd.DataFrame(
            [
                {
                    AnalyseAssetsCatalog.ASSET_ID: GOLD_COINS_ROI_ASSET_ID,
                    AnalyseAssetsCatalog.OUTPUT_FILE: "a_zloto.xlsx",
                    "order": 1,
                    "enabled": True,
                    AnalyseAssetsCatalog.POOL_ID: DEFAULT_POOL_ID,
                },
            ]
        )
        rules = pd.DataFrame(
            [
                {
                    AnalyseAssetsRules.ASSET_ID: GOLD_COINS_ROI_ASSET_ID,
                    AnalyseAssetsRules.STEP_ID: "revolut_buy",
                    AnalyseAssetsRules.STEP_ORDER: 0,
                    AnalyseAssetsRules.MAPPING: "initial_investment",
                    AnalyseAssetsRules.CONDITION_GROUP: 1,
                    AnalyseAssetsRules.FIELD: "TITLE",
                    AnalyseAssetsRules.OPERATOR: "contains",
                    AnalyseAssetsRules.VALUE: "Grupa Goldenmark",
                    AnalyseAssetsRules.POOL_ID: REVOLUT_PLN,
                },
                {
                    AnalyseAssetsRules.ASSET_ID: GOLD_COINS_ROI_ASSET_ID,
                    AnalyseAssetsRules.STEP_ID: "mbank_buy",
                    AnalyseAssetsRules.STEP_ORDER: 1,
                    AnalyseAssetsRules.MAPPING: "initial_investment",
                    AnalyseAssetsRules.CONDITION_GROUP: 1,
                    AnalyseAssetsRules.FIELD: "TITLE",
                    AnalyseAssetsRules.OPERATOR: "contains",
                    AnalyseAssetsRules.VALUE: "GOLDENMARK",
                    AnalyseAssetsRules.POOL_ID: "",
                },
            ]
        )
        manual = pd.DataFrame(columns=list(AnalyseAssetsManual.expected_columns()))

        events_by_asset, unallocated = allocate_catalog(pool, catalog, rules, manual)
        events = events_by_asset[GOLD_COINS_ROI_ASSET_ID]

        self.assertEqual(len(events), 2)
        by_source = {
            str(row[CashFlowEvent.SOURCE]): float(row[CashFlowEvent.AMOUNT])
            for _, row in events.iterrows()
        }
        self.assertAlmostEqual(by_source[REVOLUT_PLN], -35438.0)
        self.assertAlmostEqual(by_source[DEFAULT_POOL_ID], -34278.0)
        self.assertTrue((events[CashFlowEvent.CATEGORY] == CAPEX).all())
        self.assertEqual(len(unallocated), 1)


if __name__ == "__main__":
    unittest.main()
