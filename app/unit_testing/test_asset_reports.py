# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

import pandas as pd

from asset_reports import format_rap_table, rap1
from importers.assets.data_model import AssetsDef
from importers.degiro.data_model import DEFAULT_DEGIRO_ASSET_ID
from portfolios.assignment import (
    PORTFOLIO_CASH_POOL,
    PORTFOLIO_DLUGOTERMINOWY,
    PORTFOLIO_GM,
    PORTFOLIO_REVOLUT_ROBO,
)


def _row(asset_id: str, typ: str, group: str, currency: str, value: float, value_pln: float) -> dict:
    return {
        AssetsDef.ID: asset_id,
        AssetsDef.TYPE: typ,
        AssetsDef.GROUP: group,
        AssetsDef.CURRENCY: currency,
        AssetsDef.VALUE: value,
        AssetsDef.VALUE_PLN: value_pln,
    }


class RapPortfolioIndexTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = pd.DataFrame(
            [
                _row(DEFAULT_DEGIRO_ASSET_ID, "investment.udziały", "5 inwestycje finansowe", "EUR", 100, 400),
                _row("p_re_robo", "investment.udziały", "5 inwestycje finansowe", "EUR", 50, 200),
                _row("p_m_23_2330", "cash_pool.ror", "1 konta bankowe", "PLN", 999, 999),
                _row("cash", "investment.cash", "0 gotówka", "EUR", 10, 40),
            ]
        )

    def test_rap1_is_portfolio_razem_and_share(self):
        table = rap1(self.snapshot)
        self.assertEqual(list(table.columns), ["RAZEM", "udział", "XIRR", "XIRR PLN"])
        self.assertEqual(table.index.name, AssetsDef.PORTFOLIO)
        self.assertIn(PORTFOLIO_CASH_POOL, table.index)
        self.assertIn(PORTFOLIO_GM, table.index)
        self.assertIn(PORTFOLIO_REVOLUT_ROBO, table.index)
        self.assertIn(PORTFOLIO_DLUGOTERMINOWY, table.index)
        self.assertIn("Z RAZEM", table.index)
        # 999 + 400 + 200 + 40 = 1639
        self.assertEqual(str(table.loc[PORTFOLIO_CASH_POOL, "RAZEM"]).strip(), "999")
        self.assertEqual(str(table.loc[PORTFOLIO_GM, "RAZEM"]).strip(), "400")
        self.assertEqual(str(table.loc[PORTFOLIO_REVOLUT_ROBO, "RAZEM"]).strip(), "200")
        self.assertEqual(str(table.loc[PORTFOLIO_DLUGOTERMINOWY, "RAZEM"]).strip(), "40")
        self.assertEqual(str(table.loc["Z RAZEM", "RAZEM"]).strip(), "1 639")
        self.assertEqual(str(table.loc["Z RAZEM", "udział"]).strip(), "100.0%")
        self.assertEqual(str(table.loc[PORTFOLIO_CASH_POOL, "udział"]).strip(), "61.0%")
        self.assertEqual(str(table.loc[PORTFOLIO_GM, "udział"]).strip(), "24.4%")
        self.assertEqual(str(table.loc[PORTFOLIO_GM, "XIRR"]).strip(), "—")
        self.assertEqual(str(table.loc["Z RAZEM", "XIRR"]).strip(), "—")
        self.assertEqual(str(table.loc[PORTFOLIO_GM, "XIRR PLN"]).strip(), "—")
        self.assertEqual(str(table.loc["Z RAZEM", "XIRR PLN"]).strip(), "—")
        self.assertNotIn("EUR", table.columns)
        self.assertNotIn("PLN", table.columns)

    def test_rap1_formats_portfolio_xirr_column(self):
        table = rap1(
            self.snapshot,
            xirr_by_portfolio={
                PORTFOLIO_CASH_POOL: None,
                PORTFOLIO_GM: 0.1234,
                PORTFOLIO_REVOLUT_ROBO: -0.05,
                PORTFOLIO_DLUGOTERMINOWY: 0.0,
                "Z RAZEM": 0.08,
            },
            xirr_pln_by_portfolio={
                PORTFOLIO_CASH_POOL: None,
                PORTFOLIO_GM: 0.15,
                PORTFOLIO_REVOLUT_ROBO: -0.08,
                PORTFOLIO_DLUGOTERMINOWY: 0.01,
                "Z RAZEM": 0.09,
            },
        )
        self.assertEqual(str(table.loc[PORTFOLIO_CASH_POOL, "XIRR"]).strip(), "—")
        self.assertEqual(str(table.loc[PORTFOLIO_GM, "XIRR"]).strip(), "12.3%")
        self.assertEqual(str(table.loc[PORTFOLIO_REVOLUT_ROBO, "XIRR"]).strip(), "-5.0%")
        self.assertEqual(str(table.loc[PORTFOLIO_DLUGOTERMINOWY, "XIRR"]).strip(), "0.0%")
        self.assertEqual(str(table.loc["Z RAZEM", "XIRR"]).strip(), "8.0%")
        self.assertEqual(str(table.loc[PORTFOLIO_GM, "XIRR PLN"]).strip(), "15.0%")
        self.assertEqual(str(table.loc[PORTFOLIO_REVOLUT_ROBO, "XIRR PLN"]).strip(), "-8.0%")
        self.assertEqual(str(table.loc[PORTFOLIO_DLUGOTERMINOWY, "XIRR PLN"]).strip(), "1.0%")
        self.assertEqual(str(table.loc["Z RAZEM", "XIRR PLN"]).strip(), "9.0%")
        self.assertEqual(str(table.loc[PORTFOLIO_CASH_POOL, "XIRR PLN"]).strip(), "—")

    def test_rap_table_headers_sit_above_values(self):
        table = pd.DataFrame(
            {
                "RAZEM": ["1 639"],
                "udział": ["100.0%"],
            },
            index=pd.Index(["Z RAZEM"], name="portfel"),
        )
        lines = format_rap_table(table).splitlines()
        header, _names, data = lines
        for col, value in (
            ("RAZEM", "1 639"),
            ("udział", "100.0%"),
        ):
            header_end = header.rfind(col) + len(col)
            value_end = data.rfind(value) + len(value)
            self.assertEqual(header_end, value_end, f"{col!r} vs {value!r}\n{header}\n{data}")
