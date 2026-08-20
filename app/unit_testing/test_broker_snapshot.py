# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from evaluators.broker_registry import (
    BROKER_SNAPSHOT_EVALUATORS,
    resolve_broker_snapshot_evaluator,
)
from evaluators.broker_snapshot import (
    BrokerHoldings,
    BrokerSnapshotEvaluator,
    snapshot_from_holdings,
    unknown_broker_warning,
)
from evaluators.evaluate_assets import evaluate_assets
from evaluators.evaluate_broker_degiro import DegiroSnapshotEvaluator
from evaluators.evaluate_broker_revolut import RevolutRoboSnapshotEvaluator
from evaluators.evaluate_broker_traderepublic import TradeRepublicSnapshotEvaluator
from evaluators.evaluate_broker_xtb import XtbSnapshotEvaluator
from importers.assets.data_model import AssetsDef, GroupDomain, KindDomain, TypeDomain
from importers.degiro.data_model import DEFAULT_DEGIRO_ASSET_ID
from importers.revolut.trading_data_model import DEFAULT_REVOLUT_ROBO_ASSET_ID
from importers.traderepublic.data_model import DEFAULT_TRADEREPUBLIC_ASSET_ID
from importers.xtb.data_model import DEFAULT_XTB_ASSET_ID


def _catalog(asset_id: str, descr: str = "broker") -> pd.Series:
    return pd.Series(
        {
            AssetsDef.ID: asset_id,
            AssetsDef.TYPE: TypeDomain.EQUITIES,
            AssetsDef.GROUP: GroupDomain.INVESTMENT,
            AssetsDef.DESCR: descr,
            AssetsDef.KIND: KindDomain.BROKER,
            AssetsDef.CURRENCY: "EUR",
            AssetsDef.NOTES: "",
        }
    )


class BrokerHoldingsTests(unittest.TestCase):
    def test_total_is_positions_plus_cash(self):
        holdings = BrokerHoldings(
            positions_value=51.0,
            cash_value=49.0,
            n_positions=2,
            n_cash_rows=1,
            evaluation_date="2026-01-31",
            currency="EUR",
        )
        self.assertAlmostEqual(holdings.total_value, 100.0)
        row = snapshot_from_holdings(_catalog("p_re_robo", "robo"), "p_re_robo", holdings)
        self.assertAlmostEqual(float(row.iloc[0][AssetsDef.VALUE]), 100.0)
        self.assertEqual(row.iloc[0][AssetsDef.DESCR], "robo (2 poz. + 1 cash)")


class BrokerRegistryTests(unittest.TestCase):
    def test_known_ids_resolve_to_dedicated_evaluators(self):
        mapping = {
            DEFAULT_DEGIRO_ASSET_ID: DegiroSnapshotEvaluator,
            DEFAULT_XTB_ASSET_ID: XtbSnapshotEvaluator,
            DEFAULT_REVOLUT_ROBO_ASSET_ID: RevolutRoboSnapshotEvaluator,
            DEFAULT_TRADEREPUBLIC_ASSET_ID: TradeRepublicSnapshotEvaluator,
        }
        for asset_id, cls in mapping.items():
            ev = resolve_broker_snapshot_evaluator(_catalog(asset_id))
            self.assertIsInstance(ev, cls)
            self.assertIsInstance(ev, BrokerSnapshotEvaluator)

    def test_registry_covers_all_equity_brokers(self):
        self.assertEqual(len(BROKER_SNAPSHOT_EVALUATORS), 4)

    def test_unknown_id_does_not_fall_back_to_revolut(self):
        self.assertIsNone(resolve_broker_snapshot_evaluator(_catalog("p_new_broker")))

    def test_evaluate_assets_warns_for_unknown_broker(self):
        assets = pd.DataFrame([_catalog("p_new_broker")])
        with patch("evaluators.evaluate_assets.get_fx_as_of") as fx:
            fx.side_effect = AssertionError("unknown broker must not reach FX")
            result, warnings = evaluate_assets(
                Path("/tmp"), assets, pd.DataFrame(), date(2026, 1, 31)
            )
        self.assertTrue(result.empty)
        self.assertEqual(warnings, [f"[p_new_broker] {unknown_broker_warning('p_new_broker')}"])


if __name__ == "__main__":
    unittest.main()
