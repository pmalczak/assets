# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

import pandas as pd

from evaluators.broker_snapshot import BrokerHoldings
from importers.assets.data_model import AssetsDef
from importers.degiro.data_model import DEFAULT_DEGIRO_ASSET_ID
from importers.xtb.data_model import DEFAULT_XTB_ASSET_ID
from portfolios.assignment import ROLE_OVERLAY, nav_pln_for_portfolio, PORTFOLIO_GM
from portfolios.composition import compose_gm_composition
from roi.gold_terminal import GOLD_COINS_ROI_ASSET_ID


def _snapshot_row(asset_id: str, value_pln: float) -> dict:
    return {
        AssetsDef.ID: asset_id,
        AssetsDef.VALUE_PLN: value_pln,
        AssetsDef.VALUE: value_pln,
        AssetsDef.GROUP: "5 inwestycje finansowe",
    }


class GmCompositionTests(unittest.TestCase):
    def test_nav_and_weights_and_overlay_split(self):
        snapshot = pd.DataFrame(
            [
                _snapshot_row(DEFAULT_DEGIRO_ASSET_ID, 400.0),
                _snapshot_row(DEFAULT_XTB_ASSET_ID, 300.0),
                _snapshot_row(GOLD_COINS_ROI_ASSET_ID, 300.0),
                _snapshot_row("p_re_robo", 999.0),
            ]
        )
        self.assertAlmostEqual(nav_pln_for_portfolio(snapshot, PORTFOLIO_GM), 1000.0)
        table = compose_gm_composition(snapshot)
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
        table = compose_gm_composition(snapshot, holdings)
        degiro = table.loc[table["id"] == DEFAULT_DEGIRO_ASSET_ID].iloc[0]
        self.assertAlmostEqual(float(degiro["Pozycje PLN"]), 160.0)
        self.assertAlmostEqual(float(degiro["Gotówka PLN"]), 40.0)

    def test_missing_snapshot_rows_stay_in_table(self):
        table = compose_gm_composition(pd.DataFrame())
        self.assertEqual(len(table), 3)
        self.assertFalse(bool(table["w_snapshocie"].any()))
        self.assertAlmostEqual(float(table["NAV PLN"].sum()), 0.0)


if __name__ == "__main__":
    unittest.main()
