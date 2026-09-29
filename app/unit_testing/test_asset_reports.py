# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

import pandas as pd

from asset_reports import format_rap_table, rap1, rap2
from importers.assets.data_model import AssetsDef
from importers.degiro.data_model import DEFAULT_DEGIRO_ASSET_ID
from portfolios.assignment import (
    PORTFOLIO_CASH_POOL,
    PORTFOLIO_DLUGOTERMINOWY,
    PORTFOLIO_GM,
    PORTFOLIO_PLYNNY,
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

    def test_rap2_index_is_portfolio_and_type(self):
        table = rap2(self.snapshot)
        self.assertEqual(list(table.index.names), [AssetsDef.PORTFOLIO, AssetsDef.TYPE])
        self.assertIn((PORTFOLIO_CASH_POOL, "cash_pool.ror"), table.index)
        self.assertIn((PORTFOLIO_GM, "investment.udziały"), table.index)
        self.assertIn(("Z RAZEM", "Z RAZEM"), table.index)

    def test_rap2_formats_amounts_like_rap1(self):
        snapshot = pd.concat(
            [
                self.snapshot,
                pd.DataFrame(
                    [
                        _row(
                            "obligacjeskarbowe",
                            "investment.obligacje",
                            "5 inwestycje finansowe",
                            "PLN",
                            1234,
                            1234,
                        )
                    ]
                ),
            ],
            ignore_index=True,
        )
        table = rap2(snapshot)
        gm = table.loc[(PORTFOLIO_GM, "investment.udziały")]
        self.assertEqual(str(gm["wartość_eur"]).strip(), "100")
        self.assertEqual(str(gm["wartość_pln"]).strip(), "0")
        self.assertEqual(str(gm["wartość-pln_eur"]).strip(), "400")
        self.assertEqual(str(gm["wartość-pln_pln"]).strip(), "0")
        bonds = table.loc[(PORTFOLIO_DLUGOTERMINOWY, "investment.obligacje")]
        self.assertEqual(str(bonds["wartość_pln"]).strip(), "1 234")
        self.assertEqual(str(gm["RAZEM-PLN"]).strip(), "400")
        self.assertEqual(str(bonds["RAZEM-PLN"]).strip(), "1 234")
        cash = table.loc[(PORTFOLIO_DLUGOTERMINOWY, "investment.cash")]
        self.assertEqual(str(cash["wartość-pln_eur"]).strip(), "40")
        self.assertEqual(str(cash["RAZEM-PLN"]).strip(), "40")
        dlugo_total = table.loc[(PORTFOLIO_DLUGOTERMINOWY, "Z RAZEM")]
        self.assertEqual(str(dlugo_total["wartość-pln_eur"]).strip(), "40")
        self.assertEqual(str(dlugo_total["wartość-pln_pln"]).strip(), "1 234")
        self.assertEqual(str(dlugo_total["RAZEM-PLN"]).strip(), "1 274")
        cash_pool = table.loc[(PORTFOLIO_CASH_POOL, "Z RAZEM")]
        self.assertEqual(str(cash_pool["wartość-pln_pln"]).strip(), "999")
        self.assertEqual(str(cash_pool["RAZEM-PLN"]).strip(), "999")
        self.assertEqual(list(table.columns)[-1], "RAZEM-PLN")
        self.assertNotIn("nan", " ".join(str(v) for v in table.to_numpy().ravel()))
        self.assertNotIn(".0", " ".join(str(v) for v in table.to_numpy().ravel()))

    def test_rap2_headers_sit_above_values(self):
        table = pd.DataFrame(
            {
                "wartość-pln_eur": ["40"],
                "RAZEM-PLN": ["2 273"],
            },
            index=pd.MultiIndex.from_tuples(
                [("0 PŁYNNY", "investment.cash")],
                names=["portfel", "typ"],
            ),
        )
        lines = format_rap_table(table).splitlines()
        header, _names, data = lines
        for col, value in (
            ("wartość-pln_eur", "40"),
            ("RAZEM-PLN", "2 273"),
        ):
            header_end = header.rfind(col) + len(col)
            value_end = data.rfind(value) + len(value)
            self.assertEqual(header_end, value_end, f"{col!r} vs {value!r}\n{header}\n{data}")
