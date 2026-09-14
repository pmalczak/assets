# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

import pandas as pd

from app_streamlit.column_layout import with_value_currency_pln_order
from app_streamlit.render_portfolios import _composition_table
from importers.assets.data_model import AssetsDef
from portfolios.assignment import PORTFOLIO_OGOLNY, PORTFOLIO_REVOLUT_ROBO


class ValueCurrencyPlnOrderTests(unittest.TestCase):
    def test_moves_currency_between_value_and_pln(self):
        df = pd.DataFrame(
            [
                {
                    AssetsDef.ID: "cash",
                    AssetsDef.CURRENCY: "EUR",
                    AssetsDef.VALUE: 10.0,
                    "inne": "x",
                    AssetsDef.VALUE_PLN: 40,
                }
            ]
        )
        ordered = with_value_currency_pln_order(df)
        self.assertEqual(
            list(ordered.columns),
            [AssetsDef.ID, AssetsDef.VALUE, AssetsDef.CURRENCY, AssetsDef.VALUE_PLN, "inne"],
        )

    def test_places_eval_fx_days_after_value_block(self):
        df = pd.DataFrame(
            [
                {
                    AssetsDef.ID: "cash",
                    AssetsDef.DAYS_AFTER_VALUATION: 3,
                    AssetsDef.VALUE: 10.0,
                    AssetsDef.VALUE_DATE: "2026-09-11",
                    AssetsDef.CURRENCY: "EUR",
                    AssetsDef.EVALUATION_DATE: "2026-09-01",
                    AssetsDef.VALUE_PLN: 40,
                }
            ]
        )
        ordered = with_value_currency_pln_order(df)
        self.assertEqual(
            list(ordered.columns),
            [
                AssetsDef.ID,
                AssetsDef.VALUE,
                AssetsDef.CURRENCY,
                AssetsDef.VALUE_PLN,
                AssetsDef.EVALUATION_DATE,
                AssetsDef.VALUE_DATE,
                AssetsDef.DAYS_AFTER_VALUATION,
            ],
        )

    def test_portfolios_composition_uses_value_currency_pln(self):
        snapshot = pd.DataFrame(
            [
                {
                    AssetsDef.ID: "cash",
                    AssetsDef.DESCR: "gotówka",
                    AssetsDef.TYPE: "investment.cash",
                    AssetsDef.CURRENCY: "EUR",
                    AssetsDef.VALUE: 10.0,
                    AssetsDef.VALUE_PLN: 40,
                    AssetsDef.EVALUATION_DATE: "2026-09-01",
                    AssetsDef.VALUE_DATE: "2026-09-11",
                    AssetsDef.DAYS_AFTER_VALUATION: 10,
                    AssetsDef.PORTFOLIO: PORTFOLIO_OGOLNY,
                }
            ]
        )
        table = _composition_table(snapshot, PORTFOLIO_OGOLNY)
        cols = list(table.columns)
        self.assertEqual(
            cols[cols.index(AssetsDef.VALUE) : cols.index(AssetsDef.DAYS_AFTER_VALUATION) + 1],
            [
                AssetsDef.VALUE,
                AssetsDef.CURRENCY,
                AssetsDef.VALUE_PLN,
                AssetsDef.EVALUATION_DATE,
                AssetsDef.VALUE_DATE,
                AssetsDef.DAYS_AFTER_VALUATION,
            ],
        )
        empty = _composition_table(snapshot, PORTFOLIO_REVOLUT_ROBO)
        self.assertTrue(empty.empty)
