# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

import pandas as pd

from app_proc.rejestr_views import (
    ASSET_ZLOTO,
    LAYER_STAN,
    _ike_holdings_frame,
    build_rejestr_asset,
)
from importers.assets.data_model import AssetsDef, Inventory
from importers.assets.ike import IkeInventory, IkeKurs


class IkeHoldingsFrameTests(unittest.TestCase):
    def test_per_product_nav_and_eval_date(self):
        inv = pd.DataFrame(
            {
                IkeInventory.PRODUCT: ["A", "A", "B"],
                IkeInventory.DATE: ["2020-01-01", "2020-06-01", "2020-01-01"],
                IkeInventory.UNITS: [10.0, 5.0, 2.0],
                IkeInventory.VALUE: [100.0, 60.0, 20.0],
                IkeInventory.CURRENCY: ["PLN", "PLN", "PLN"],
            }
        )
        kurs = pd.DataFrame(
            {
                IkeKurs.PRODUCT: ["A", "A", "B"],
                IkeKurs.DATE: ["2020-05-01", "2020-12-01", "2020-12-15"],
                IkeKurs.PRICE: [10.0, 12.0, 20.0],
            }
        )
        frame, total, eval_date = _ike_holdings_frame(inv, kurs, date(2021, 1, 1))
        self.assertEqual(len(frame), 2)
        by_prod = frame.set_index(IkeInventory.PRODUCT)
        self.assertAlmostEqual(float(by_prod.loc["A", "jednostki"]), 15.0)
        self.assertAlmostEqual(float(by_prod.loc["A", IkeKurs.PRICE]), 12.0)
        self.assertAlmostEqual(float(by_prod.loc["A", AssetsDef.VALUE]), 180.0)
        self.assertAlmostEqual(float(by_prod.loc["B", AssetsDef.VALUE]), 40.0)
        self.assertAlmostEqual(total, 220.0)
        self.assertEqual(eval_date, date(2020, 12, 15))


class GoldRejestrViewTests(unittest.TestCase):
    def test_stan_aggregates_and_ruchy_sorted(self):
        inventory = pd.DataFrame(
            {
                Inventory.DATE: ["2024-01-02", "2024-06-01", "2023-12-01"],
                Inventory.INSTRUMENT: ["Krugerrand", "Krugerrand", "Maple"],
                Inventory.WEIGHT: ["1oz", "1oz", "1oz"],
                Inventory.QUANTITY: [1.0, 2.0, 1.0],
                Inventory.NOTES: ["a", "b", "c"],
            }
        )
        with patch("app_proc.rejestr_views.read_inventory", return_value=inventory):
            view = build_rejestr_asset(ASSET_ZLOTO, date(2024, 12, 31))
        self.assertTrue(view.has_ruchy)
        self.assertEqual(view.stan.n_positions, 2)
        self.assertAlmostEqual(float(view.stan.extra["suma sztuk"]), 4.0)
        by_inst = view.stan.frame.set_index(Inventory.INSTRUMENT)
        self.assertAlmostEqual(float(by_inst.loc["Krugerrand", Inventory.QUANTITY]), 3.0)
        self.assertEqual(
            list(view.ruchy.frame[Inventory.DATE].astype(str)),
            ["2024-06-01", "2024-01-02", "2023-12-01"],
        )
        self.assertEqual(LAYER_STAN, "Stan")


if __name__ == "__main__":
    unittest.main()
