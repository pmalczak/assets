# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

import pandas as pd

from asset_reports import format_rap_table, rap1, rap2
from importers.assets.data_model import AssetsDef
from importers.degiro.data_model import DEFAULT_DEGIRO_ASSET_ID
from portfolios.assignment import PORTFOLIO_GM, PORTFOLIO_OGOLNY, PORTFOLIO_REVOLUT_ROBO


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

    def test_rap1_index_is_portfolio_and_group(self):
        table = rap1(self.snapshot)
        self.assertEqual(list(table.index.names), [AssetsDef.PORTFOLIO, AssetsDef.GROUP])
        self.assertIn((PORTFOLIO_OGOLNY, "1 konta bankowe"), table.index)
        self.assertIn((PORTFOLIO_GM, "5 inwestycje finansowe"), table.index)
        self.assertIn((PORTFOLIO_REVOLUT_ROBO, "5 inwestycje finansowe"), table.index)
        self.assertIn(("Z RAZEM", "Z RAZEM"), table.index)
        ogolny_bank = table.loc[(PORTFOLIO_OGOLNY, "1 konta bankowe")]
        self.assertEqual(str(ogolny_bank["PLN"]).strip(), "999")

    def test_rap2_index_is_portfolio_and_type(self):
        table = rap2(self.snapshot)
        self.assertEqual(list(table.index.names), [AssetsDef.PORTFOLIO, AssetsDef.TYPE])
        self.assertIn((PORTFOLIO_OGOLNY, "cash_pool.ror"), table.index)
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
        bonds = table.loc[(PORTFOLIO_OGOLNY, "investment.obligacje")]
        self.assertEqual(str(bonds["wartość_pln"]).strip(), "1 234")
        self.assertEqual(str(gm["RAZEM-PLN"]).strip(), "400")
        self.assertEqual(str(bonds["RAZEM-PLN"]).strip(), "1 234")
        mixed = table.loc[(PORTFOLIO_OGOLNY, "Z RAZEM")]
        self.assertEqual(str(mixed["wartość-pln_eur"]).strip(), "40")
        self.assertEqual(str(mixed["wartość-pln_pln"]).strip(), "2 233")
        self.assertEqual(str(mixed["RAZEM-PLN"]).strip(), "2 273")
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
                [("0 OGÓLNY", "investment.cash")],
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
