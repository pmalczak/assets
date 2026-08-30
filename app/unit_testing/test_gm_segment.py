# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

from evaluators.broker_snapshot import BrokerHoldings
from gm_segment.segment import (
    GM_SEGMENT,
    ROLE_EXECUTION,
    ROLE_OVERLAY,
    compose_gm_segment_table,
    gm_segment_nav_pln,
    gm_segment_role,
    load_gm_segment_nav_history,
    nav_path_metrics,
    rebased_overlap,
    segment_for_asset_id,
)
from importers.assets.data_model import AssetsDef
from importers.degiro.data_model import DEFAULT_DEGIRO_ASSET_ID
from importers.xtb.data_model import DEFAULT_XTB_ASSET_ID
from portfolios.assignment import PORTFOLIO_GM
from roi.gold_terminal import GOLD_COINS_ROI_ASSET_ID


def _snapshot_row(asset_id: str, value_pln: float) -> dict:
    return {
        AssetsDef.ID: asset_id,
        AssetsDef.VALUE_PLN: value_pln,
        AssetsDef.VALUE: value_pln,
        AssetsDef.GROUP: "5 inwestycje finansowe",
    }


class GmSegmentTagTests(unittest.TestCase):
    def test_known_ids_are_gm_segment(self):
        self.assertEqual(segment_for_asset_id(DEFAULT_DEGIRO_ASSET_ID), GM_SEGMENT)
        self.assertEqual(segment_for_asset_id(DEFAULT_XTB_ASSET_ID), GM_SEGMENT)
        self.assertEqual(segment_for_asset_id(GOLD_COINS_ROI_ASSET_ID), GM_SEGMENT)
        self.assertIsNone(segment_for_asset_id("p_re_robo"))
        self.assertIsNone(segment_for_asset_id("cash"))

    def test_gold_is_overlay_brokers_are_execution(self):
        self.assertEqual(gm_segment_role(GOLD_COINS_ROI_ASSET_ID), ROLE_OVERLAY)
        self.assertEqual(gm_segment_role(DEFAULT_DEGIRO_ASSET_ID), ROLE_EXECUTION)
        self.assertEqual(gm_segment_role(DEFAULT_XTB_ASSET_ID), ROLE_EXECUTION)
        self.assertIsNone(gm_segment_role("obligacjeskarbowe"))


class GmSegmentComposeTests(unittest.TestCase):
    def test_nav_and_weights_and_overlay_split(self):
        snapshot = pd.DataFrame(
            [
                _snapshot_row(DEFAULT_DEGIRO_ASSET_ID, 400.0),
                _snapshot_row(DEFAULT_XTB_ASSET_ID, 300.0),
                _snapshot_row(GOLD_COINS_ROI_ASSET_ID, 300.0),
                _snapshot_row("p_re_robo", 999.0),
            ]
        )
        self.assertAlmostEqual(gm_segment_nav_pln(snapshot), 1000.0)
        table = compose_gm_segment_table(snapshot)
        self.assertEqual(list(table["id"]), [
            DEFAULT_DEGIRO_ASSET_ID,
            DEFAULT_XTB_ASSET_ID,
            GOLD_COINS_ROI_ASSET_ID,
        ])
        self.assertAlmostEqual(float(table["Udział"].sum()), 1.0)
        gold = table.loc[table["id"] == GOLD_COINS_ROI_ASSET_ID].iloc[0]
        self.assertEqual(gold["Rola"], ROLE_OVERLAY)
        self.assertAlmostEqual(float(gold["Pozycje PLN"]), 300.0)
        self.assertAlmostEqual(float(gold["Gotówka PLN"]), 0.0)
        degiro = table.loc[table["id"] == DEFAULT_DEGIRO_ASSET_ID].iloc[0]
        self.assertTrue(pd.isna(degiro["Pozycje PLN"]))

    def test_broker_holdings_split_uses_snapshot_pln(self):
        snapshot = pd.DataFrame(
            [
                _snapshot_row(DEFAULT_DEGIRO_ASSET_ID, 200.0),
                _snapshot_row(DEFAULT_XTB_ASSET_ID, 0.0),
                _snapshot_row(GOLD_COINS_ROI_ASSET_ID, 0.0),
            ]
        )
        holdings = {
            DEFAULT_DEGIRO_ASSET_ID: BrokerHoldings(
                positions_value=80.0,
                cash_value=20.0,
                n_positions=3,
                n_cash_rows=1,
                evaluation_date="2026-08-01",
                currency="EUR",
            )
        }
        table = compose_gm_segment_table(snapshot, holdings)
        degiro = table.loc[table["id"] == DEFAULT_DEGIRO_ASSET_ID].iloc[0]
        self.assertAlmostEqual(float(degiro["Pozycje PLN"]), 160.0)
        self.assertAlmostEqual(float(degiro["Gotówka PLN"]), 40.0)

    def test_missing_snapshot_rows_stay_in_table(self):
        table = compose_gm_segment_table(pd.DataFrame())
        self.assertEqual(len(table), 3)
        self.assertFalse(bool(table["w_snapshocie"].any()))
        self.assertAlmostEqual(float(table["NAV PLN"].sum()), 0.0)


class GmSegmentHistoryTests(unittest.TestCase):
    def test_nav_history_sums_segment_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_snapshot(
                root,
                date(2026, 8, 1),
                [
                    _snapshot_row(DEFAULT_DEGIRO_ASSET_ID, 100.0),
                    _snapshot_row(GOLD_COINS_ROI_ASSET_ID, 50.0),
                ],
            )
            _write_snapshot(
                root,
                date(2026, 8, 8),
                [
                    _snapshot_row(DEFAULT_DEGIRO_ASSET_ID, 110.0),
                    _snapshot_row(DEFAULT_XTB_ASSET_ID, 40.0),
                    _snapshot_row(GOLD_COINS_ROI_ASSET_ID, 50.0),
                    _snapshot_row("p_re_robo", 800.0),
                ],
            )
            history = load_gm_segment_nav_history(root)
        self.assertEqual(list(history.values), [150.0, 200.0])

    def test_nav_path_metrics_and_rebase(self):
        nav = pd.Series(
            [100.0, 110.0, 105.0],
            index=pd.to_datetime(["2026-01-31", "2026-02-28", "2026-03-31"]),
            name=f"Portfel {PORTFOLIO_GM} NAV",
        )
        metrics = nav_path_metrics(nav)
        self.assertAlmostEqual(metrics["Total Return"], 0.05)
        self.assertLess(metrics["Max Drawdown"], 0)
        u7 = pd.Series(
            [10_000.0, 10_500.0, 11_000.0],
            index=pd.to_datetime(["2026-01-31", "2026-02-28", "2026-03-31"]),
            name="GM U7",
        )
        rebased = rebased_overlap(nav, u7)
        self.assertAlmostEqual(float(rebased.iloc[0, 0]), 100.0)
        self.assertAlmostEqual(float(rebased.iloc[0, 1]), 100.0)
        self.assertAlmostEqual(float(rebased.iloc[-1][f"Portfel {PORTFOLIO_GM} NAV"]), 105.0)
        self.assertAlmostEqual(float(rebased.iloc[-1]["GM U7"]), 110.0)


def _write_snapshot(directory: Path, snapshot_date: date, rows: list[dict]) -> None:
    pd.DataFrame(rows).to_parquet(directory / f"{snapshot_date.isoformat()}.parquet")


if __name__ == "__main__":
    unittest.main()
