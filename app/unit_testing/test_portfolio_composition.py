# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

import pandas as pd

from evaluators.broker_snapshot import BrokerHoldings
from importers.assets.data_model import AssetsDef
from importers.degiro.data_model import DEFAULT_DEGIRO_ASSET_ID
from importers.xtb.data_model import DEFAULT_XTB_ASSET_ID
from portfolios.assignment import ROLE_EXECUTION, nav_pln_for_portfolio, PORTFOLIO_GM
from portfolios.composition import (
    KIND_CASH,
    KIND_POSITION,
    GmPositionLine,
    compose_gm_composition,
    compose_gm_instrument_composition,
)
from roi.gold_terminal import GOLD_COINS_ROI_ASSET_ID


def _snapshot_row(asset_id: str, value_pln: float, *, value: float | None = None, currency: str = "EUR") -> dict:
    native = value if value is not None else (value_pln / 4 if value_pln else 0.0)
    return {
        AssetsDef.ID: asset_id,
        AssetsDef.VALUE_PLN: value_pln,
        AssetsDef.VALUE: native,
        AssetsDef.CURRENCY: currency,
        AssetsDef.GROUP: "5 inwestycje finansowe",
    }


class GmCompositionTests(unittest.TestCase):
    def test_nav_and_weights_brokers_only(self):
        snapshot = pd.DataFrame(
            [
                _snapshot_row(DEFAULT_DEGIRO_ASSET_ID, 400.0),
                _snapshot_row(DEFAULT_XTB_ASSET_ID, 300.0),
                _snapshot_row(GOLD_COINS_ROI_ASSET_ID, 300.0),
                _snapshot_row("p_re_robo", 999.0),
            ]
        )
        self.assertAlmostEqual(nav_pln_for_portfolio(snapshot, PORTFOLIO_GM), 700.0)
        table = compose_gm_composition(snapshot)
        cols = list(table.columns)
        self.assertEqual(
            cols[cols.index(AssetsDef.VALUE): cols.index(AssetsDef.DAYS_AFTER_VALUATION) + 1],
            [
                AssetsDef.VALUE,
                AssetsDef.CURRENCY,
                AssetsDef.VALUE_PLN,
                AssetsDef.EVALUATION_DATE,
                AssetsDef.VALUE_DATE,
                AssetsDef.DAYS_AFTER_VALUATION,
            ],
        )
        self.assertEqual(list(table["id"]), [
            DEFAULT_DEGIRO_ASSET_ID,
            DEFAULT_XTB_ASSET_ID,
        ])
        self.assertAlmostEqual(float(table["Udział"].sum()), 1.0)
        self.assertTrue((table["Rola"] == ROLE_EXECUTION).all())
        degiro = table.loc[table["id"] == DEFAULT_DEGIRO_ASSET_ID].iloc[0]
        self.assertTrue(pd.isna(degiro["Pozycje PLN"]))

    def test_broker_holdings_split_uses_snapshot_pln(self):
        snapshot = pd.DataFrame(
            [
                _snapshot_row(DEFAULT_DEGIRO_ASSET_ID, 200.0),
                _snapshot_row(DEFAULT_XTB_ASSET_ID, 0.0),
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
        self.assertEqual(len(table), 2)
        self.assertFalse(bool(table["w_snapshocie"].any()))
        self.assertAlmostEqual(float(table[AssetsDef.VALUE_PLN].sum()), 0.0)


class GmInstrumentCompositionTests(unittest.TestCase):
    def test_three_equal_positions_are_one_third_each(self):
        # DEGIRO: 100 EUR → 400 PLN; XTB: 200 PLN; NAV GM = 600.
        snapshot = pd.DataFrame(
            [
                _snapshot_row(DEFAULT_DEGIRO_ASSET_ID, 400.0, value=100.0, currency="EUR"),
                _snapshot_row(DEFAULT_XTB_ASSET_ID, 200.0, value=200.0, currency="PLN"),
            ]
        )
        lines = [
            GmPositionLine(
                broker_id=DEFAULT_DEGIRO_ASSET_ID,
                broker_label="DEGIRO",
                kind=KIND_POSITION,
                code="ISIN-A",
                label="Asset A",
                value=50.0,
                currency="EUR",
                evaluation_date="2026-09-01",
            ),
            GmPositionLine(
                broker_id=DEFAULT_DEGIRO_ASSET_ID,
                broker_label="DEGIRO",
                kind=KIND_POSITION,
                code="ISIN-B",
                label="Asset B",
                value=50.0,
                currency="EUR",
                evaluation_date="2026-09-01",
            ),
            GmPositionLine(
                broker_id=DEFAULT_XTB_ASSET_ID,
                broker_label="XTB",
                kind=KIND_POSITION,
                code="TICK-C",
                label="Asset C",
                value=200.0,
                currency="PLN",
                evaluation_date="2026-09-01",
            ),
        ]
        table = compose_gm_instrument_composition(snapshot, lines)
        self.assertEqual(set(table["Składnik"]), {"Asset A", "Asset B", "Asset C"})
        weights = {
            row["Składnik"]: float(row["Udział"])
            for _, row in table.iterrows()
        }
        self.assertAlmostEqual(weights["Asset A"], 1 / 3)
        self.assertAlmostEqual(weights["Asset B"], 1 / 3)
        self.assertAlmostEqual(weights["Asset C"], 1 / 3)
        self.assertAlmostEqual(float(table["Udział"].sum()), 1.0)

    def test_same_instrument_merges_across_brokers(self):
        snapshot = pd.DataFrame(
            [
                _snapshot_row(DEFAULT_DEGIRO_ASSET_ID, 400.0, value=100.0, currency="EUR"),
                _snapshot_row(DEFAULT_XTB_ASSET_ID, 200.0, value=200.0, currency="PLN"),
            ]
        )
        lines = [
            GmPositionLine(
                broker_id=DEFAULT_DEGIRO_ASSET_ID,
                broker_label="DEGIRO",
                kind=KIND_POSITION,
                code="ISIN-X",
                label="Shared",
                value=100.0,
                currency="EUR",
            ),
            GmPositionLine(
                broker_id=DEFAULT_XTB_ASSET_ID,
                broker_label="XTB",
                kind=KIND_POSITION,
                code="TICK-X",
                label="Shared",
                value=200.0,
                currency="PLN",
            ),
        ]
        table = compose_gm_instrument_composition(snapshot, lines)
        self.assertEqual(len(table), 1)
        row = table.iloc[0]
        self.assertEqual(row["Składnik"], "Shared")
        self.assertEqual(row["Konto"], "DEGIRO+XTB")
        self.assertAlmostEqual(float(row[AssetsDef.VALUE_PLN]), 600.0)
        self.assertAlmostEqual(float(row["Udział"]), 1.0)

    def test_cash_rows_are_separate_and_sorted_last(self):
        snapshot = pd.DataFrame(
            [
                _snapshot_row(DEFAULT_DEGIRO_ASSET_ID, 440.0, value=110.0, currency="EUR"),
            ]
        )
        lines = [
            GmPositionLine(
                broker_id=DEFAULT_DEGIRO_ASSET_ID,
                broker_label="DEGIRO",
                kind=KIND_CASH,
                code="",
                label="Gotówka (DEGIRO)",
                value=10.0,
                currency="EUR",
            ),
            GmPositionLine(
                broker_id=DEFAULT_DEGIRO_ASSET_ID,
                broker_label="DEGIRO",
                kind=KIND_POSITION,
                code="ISIN-A",
                label="Asset A",
                value=100.0,
                currency="EUR",
            ),
        ]
        table = compose_gm_instrument_composition(snapshot, lines)
        self.assertEqual(list(table["Składnik"]), ["Asset A", "Gotówka (DEGIRO)"])
        self.assertEqual(list(table["kind"]), [KIND_POSITION, KIND_CASH])
        self.assertAlmostEqual(float(table.iloc[0]["Udział"]), 400 / 440)
        self.assertAlmostEqual(float(table.iloc[1]["Udział"]), 40 / 440)


if __name__ == "__main__":
    unittest.main()
