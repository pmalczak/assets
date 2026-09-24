# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

import pandas as pd

from app_streamlit.column_layout import (
    amount_column_config,
    format_amount_columns,
    format_amount_display,
    with_value_currency_pln_order,
)
from app_streamlit.render_portfolios import _composition_table
from importers.assets.data_model import AssetsDef
from portfolios.assignment import PORTFOLIO_PLYNNY, PORTFOLIO_REVOLUT_ROBO


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
                    AssetsDef.PORTFOLIO: PORTFOLIO_PLYNNY,
                }
            ]
        )
        table = _composition_table(snapshot, PORTFOLIO_PLYNNY)
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


class AmountDisplayFormatTests(unittest.TestCase):
    def test_space_thousands_without_decimals(self):
        self.assertEqual(format_amount_display(1234.6), "1 235")
        self.assertEqual(format_amount_display(1_234_567), "1 234 567")
        self.assertEqual(format_amount_display(-1200), "-1 200")
        self.assertEqual(format_amount_display(None), "")

    def test_formats_value_and_value_pln_columns(self):
        df = pd.DataFrame(
            [
                {
                    AssetsDef.VALUE: 1234.2,
                    AssetsDef.VALUE_PLN: 4_321.8,
                    AssetsDef.CURRENCY: "EUR",
                }
            ]
        )
        shown = format_amount_columns(df)
        self.assertEqual(shown[AssetsDef.VALUE].iloc[0], "1 234")
        self.assertEqual(shown[AssetsDef.VALUE_PLN].iloc[0], "4 322")
        self.assertEqual(shown[AssetsDef.CURRENCY].iloc[0], "EUR")

    def test_amount_columns_are_right_aligned(self):
        df = pd.DataFrame(
            [
                {
                    AssetsDef.VALUE: "1 234",
                    AssetsDef.CURRENCY: "EUR",
                    AssetsDef.VALUE_PLN: "4 322",
                }
            ]
        )
        config = amount_column_config(df, {AssetsDef.CURRENCY: "waluta"})
        self.assertEqual(
            sorted(k for k in config if k != AssetsDef.CURRENCY),
            sorted([AssetsDef.VALUE, AssetsDef.VALUE_PLN]),
        )
        for name in (AssetsDef.VALUE, AssetsDef.VALUE_PLN):
            self.assertEqual(config[name]["alignment"], "right")
        self.assertEqual(config[AssetsDef.CURRENCY], "waluta")
