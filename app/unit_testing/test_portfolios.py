# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

from importers.assets.data_model import AssetsDef
from importers.degiro.data_model import DEFAULT_DEGIRO_ASSET_ID
from importers.revolut.trading_data_model import DEFAULT_REVOLUT_ROBO_ASSET_ID
from importers.xtb.data_model import DEFAULT_XTB_ASSET_ID
from portfolios.assignment import (
    DEFAULT_PORTFOLIO,
    PORTFOLIO_GM,
    PORTFOLIO_OGOLNY,
    PORTFOLIO_REVOLUT_ROBO,
    ROLE_EXECUTION,
    ROLE_OVERLAY,
    assets_in_portfolio,
    attach_portfolio_column,
    gm_asset_role,
    investments_by_portfolio,
    investments_with_portfolio,
    load_portfolio_nav_history,
    portfolio_for_asset_id,
    portfolio_for_row,
    portfolio_nav_pln,
)
from portfolios.nav_path import nav_path_metrics, rebased_overlap
from roi.gold_terminal import GOLD_COINS_ROI_ASSET_ID


class PortfolioAssignmentTests(unittest.TestCase):
    def test_known_membership_and_default(self):
        self.assertEqual(portfolio_for_asset_id(DEFAULT_DEGIRO_ASSET_ID), PORTFOLIO_GM)
        self.assertEqual(portfolio_for_asset_id(DEFAULT_XTB_ASSET_ID), PORTFOLIO_GM)
        self.assertEqual(portfolio_for_asset_id(GOLD_COINS_ROI_ASSET_ID), PORTFOLIO_GM)
        self.assertEqual(
            portfolio_for_asset_id(DEFAULT_REVOLUT_ROBO_ASSET_ID),
            PORTFOLIO_REVOLUT_ROBO,
        )
        self.assertEqual(portfolio_for_asset_id("cash"), PORTFOLIO_OGOLNY)
        self.assertEqual(portfolio_for_asset_id("obligacjeskarbowe"), PORTFOLIO_OGOLNY)
        self.assertEqual(portfolio_for_asset_id("nowe-aktywo"), DEFAULT_PORTFOLIO)

    def test_gm_roles_execution_vs_overlay(self):
        self.assertEqual(gm_asset_role(GOLD_COINS_ROI_ASSET_ID), ROLE_OVERLAY)
        self.assertEqual(gm_asset_role(DEFAULT_DEGIRO_ASSET_ID), ROLE_EXECUTION)
        self.assertEqual(gm_asset_role(DEFAULT_XTB_ASSET_ID), ROLE_EXECUTION)
        self.assertIsNone(gm_asset_role("obligacjeskarbowe"))
        self.assertIsNone(gm_asset_role(DEFAULT_REVOLUT_ROBO_ASSET_ID))

    def test_cash_pool_defaults_to_ogolny(self):
        self.assertEqual(portfolio_for_row("p_m_23_2330", "cash_pool.ror"), PORTFOLIO_OGOLNY)
        self.assertEqual(portfolio_for_row("cash", "investment.cash"), PORTFOLIO_OGOLNY)
        self.assertEqual(
            portfolio_for_row(DEFAULT_REVOLUT_ROBO_ASSET_ID, "investment.udziały"),
            PORTFOLIO_REVOLUT_ROBO,
        )

    def test_attach_and_nav_by_portfolio(self):
        snapshot = pd.DataFrame(
            [
                {
                    AssetsDef.ID: DEFAULT_DEGIRO_ASSET_ID,
                    AssetsDef.TYPE: "investment.udziały",
                    AssetsDef.GROUP: "5 inwestycje finansowe",
                    AssetsDef.VALUE_PLN: 400,
                },
                {
                    AssetsDef.ID: DEFAULT_REVOLUT_ROBO_ASSET_ID,
                    AssetsDef.TYPE: "investment.udziały",
                    AssetsDef.GROUP: "5 inwestycje finansowe",
                    AssetsDef.VALUE_PLN: 100,
                },
                {
                    AssetsDef.ID: "cash",
                    AssetsDef.TYPE: "investment.cash",
                    AssetsDef.GROUP: "0 gotówka",
                    AssetsDef.VALUE_PLN: 50,
                },
                {
                    AssetsDef.ID: "p_m_23_2330",
                    AssetsDef.TYPE: "cash_pool.ror",
                    AssetsDef.GROUP: "1 konta bankowe",
                    AssetsDef.VALUE_PLN: 999,
                },
            ]
        )
        stamped = attach_portfolio_column(snapshot)
        self.assertEqual(
            stamped.loc[stamped[AssetsDef.ID] == "p_m_23_2330", AssetsDef.PORTFOLIO].iloc[0],
            PORTFOLIO_OGOLNY,
        )
        investments = investments_with_portfolio(snapshot)
        self.assertNotIn("p_m_23_2330", investments[AssetsDef.ID].tolist())
        self.assertEqual(
            list(investments[AssetsDef.PORTFOLIO]),
            [PORTFOLIO_GM, PORTFOLIO_REVOLUT_ROBO, PORTFOLIO_OGOLNY],
        )
        nav = portfolio_nav_pln(snapshot)
        by_name = dict(zip(nav[AssetsDef.PORTFOLIO], nav[AssetsDef.VALUE_PLN]))
        self.assertAlmostEqual(float(by_name[PORTFOLIO_GM]), 400.0)
        self.assertAlmostEqual(float(by_name[PORTFOLIO_REVOLUT_ROBO]), 100.0)
        self.assertAlmostEqual(float(by_name[PORTFOLIO_OGOLNY]), 1049.0)

    def test_investments_split_into_three_portfolio_tables(self):
        snapshot = pd.DataFrame(
            [
                {
                    AssetsDef.ID: DEFAULT_DEGIRO_ASSET_ID,
                    AssetsDef.TYPE: "investment.udziały",
                    AssetsDef.GROUP: "5 inwestycje finansowe",
                    AssetsDef.VALUE_PLN: 400,
                },
                {
                    AssetsDef.ID: DEFAULT_REVOLUT_ROBO_ASSET_ID,
                    AssetsDef.TYPE: "investment.udziały",
                    AssetsDef.GROUP: "5 inwestycje finansowe",
                    AssetsDef.VALUE_PLN: 100,
                },
                {
                    AssetsDef.ID: "cash",
                    AssetsDef.TYPE: "investment.cash",
                    AssetsDef.GROUP: "0 gotówka",
                    AssetsDef.VALUE_PLN: 50,
                },
                {
                    AssetsDef.ID: "p_m_23_2330",
                    AssetsDef.TYPE: "cash_pool.ror",
                    AssetsDef.GROUP: "1 konta bankowe",
                    AssetsDef.VALUE_PLN: 999,
                },
            ]
        )
        tables = investments_by_portfolio(snapshot)
        names = [name for name, _ in tables]
        self.assertEqual(names, [PORTFOLIO_OGOLNY, PORTFOLIO_REVOLUT_ROBO, PORTFOLIO_GM])
        by_name = {name: frame for name, frame in tables}
        self.assertEqual(list(by_name[PORTFOLIO_OGOLNY][AssetsDef.ID]), ["cash"])
        self.assertEqual(
            list(by_name[PORTFOLIO_REVOLUT_ROBO][AssetsDef.ID]),
            [DEFAULT_REVOLUT_ROBO_ASSET_ID],
        )
        self.assertEqual(list(by_name[PORTFOLIO_GM][AssetsDef.ID]), [DEFAULT_DEGIRO_ASSET_ID])
        for _, frame in tables:
            self.assertNotIn(AssetsDef.PORTFOLIO, frame.columns)
            self.assertNotIn("p_m_23_2330", frame.get(AssetsDef.ID, pd.Series(dtype=str)).tolist())

    def test_investments_by_portfolio_keeps_empty_tables(self):
        snapshot = pd.DataFrame(
            [
                {
                    AssetsDef.ID: "cash",
                    AssetsDef.TYPE: "investment.cash",
                    AssetsDef.GROUP: "0 gotówka",
                    AssetsDef.VALUE_PLN: 50,
                },
            ]
        )
        tables = investments_by_portfolio(snapshot)
        by_name = {name: frame for name, frame in tables}
        self.assertEqual(len(by_name[PORTFOLIO_OGOLNY]), 1)
        self.assertTrue(by_name[PORTFOLIO_REVOLUT_ROBO].empty)
        self.assertTrue(by_name[PORTFOLIO_GM].empty)

    def test_ogolny_composition_includes_cash_pool(self):
        snapshot = pd.DataFrame(
            [
                {
                    AssetsDef.ID: "cash",
                    AssetsDef.TYPE: "investment.cash",
                    AssetsDef.GROUP: "0 gotówka",
                    AssetsDef.DESCR: "gotówka",
                    AssetsDef.VALUE_PLN: 50,
                },
                {
                    AssetsDef.ID: "p_m_23_2330",
                    AssetsDef.TYPE: "cash_pool.ror",
                    AssetsDef.GROUP: "1 konta bankowe",
                    AssetsDef.DESCR: "ROR",
                    AssetsDef.VALUE_PLN: 999,
                },
                {
                    AssetsDef.ID: DEFAULT_DEGIRO_ASSET_ID,
                    AssetsDef.TYPE: "investment.udziały",
                    AssetsDef.GROUP: "5 inwestycje finansowe",
                    AssetsDef.DESCR: "DEGIRO",
                    AssetsDef.VALUE_PLN: 400,
                },
            ]
        )
        ogolny = assets_in_portfolio(snapshot, PORTFOLIO_OGOLNY)
        self.assertEqual(set(ogolny[AssetsDef.ID]), {"cash", "p_m_23_2330"})
        gm = assets_in_portfolio(snapshot, PORTFOLIO_GM)
        self.assertEqual(list(gm[AssetsDef.ID]), [DEFAULT_DEGIRO_ASSET_ID])


class PortfolioNavHistoryTests(unittest.TestCase):
    def test_nav_history_splits_ogolny_vs_gm(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_snapshot(
                root,
                date(2026, 8, 1),
                [
                    _history_row(DEFAULT_DEGIRO_ASSET_ID, "investment.udziały", 100.0),
                    _history_row(GOLD_COINS_ROI_ASSET_ID, "investment.metale", 50.0),
                    _history_row("p_m_23_2330", "cash_pool.ror", 20.0),
                ],
            )
            _write_snapshot(
                root,
                date(2026, 8, 8),
                [
                    _history_row(DEFAULT_DEGIRO_ASSET_ID, "investment.udziały", 110.0),
                    _history_row(DEFAULT_XTB_ASSET_ID, "investment.udziały", 40.0),
                    _history_row(GOLD_COINS_ROI_ASSET_ID, "investment.metale", 50.0),
                    _history_row("p_m_23_2330", "cash_pool.ror", 30.0),
                    _history_row(
                        DEFAULT_REVOLUT_ROBO_ASSET_ID, "investment.udziały", 800.0
                    ),
                ],
            )
            gm = load_portfolio_nav_history(PORTFOLIO_GM, root)
            ogolny = load_portfolio_nav_history(PORTFOLIO_OGOLNY, root)
            robo = load_portfolio_nav_history(PORTFOLIO_REVOLUT_ROBO, root)
        self.assertEqual(list(gm.values), [150.0, 200.0])
        self.assertEqual(list(ogolny.values), [20.0, 30.0])
        self.assertEqual(list(robo.values), [0.0, 800.0])

    def test_nav_history_without_typ_column_still_assigns_by_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pd.DataFrame(
                [
                    {AssetsDef.ID: DEFAULT_DEGIRO_ASSET_ID, AssetsDef.VALUE_PLN: 100.0},
                    {AssetsDef.ID: "p_m_23_2330", AssetsDef.VALUE_PLN: 20.0},
                    {
                        AssetsDef.ID: DEFAULT_REVOLUT_ROBO_ASSET_ID,
                        AssetsDef.VALUE_PLN: 800.0,
                    },
                ]
            ).to_parquet(root / "2026-08-01.parquet")
            gm = load_portfolio_nav_history(PORTFOLIO_GM, root)
            ogolny = load_portfolio_nav_history(PORTFOLIO_OGOLNY, root)
            robo = load_portfolio_nav_history(PORTFOLIO_REVOLUT_ROBO, root)
        self.assertEqual(list(gm.values), [100.0])
        self.assertEqual(list(ogolny.values), [20.0])
        self.assertEqual(list(robo.values), [800.0])


class PortfolioNavPathTests(unittest.TestCase):
    def test_metrics_and_rebase(self):
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


def _history_row(asset_id: str, typ: str, value_pln: float) -> dict:
    return {
        AssetsDef.ID: asset_id,
        AssetsDef.TYPE: typ,
        AssetsDef.VALUE_PLN: value_pln,
    }


def _write_snapshot(directory: Path, snapshot_date: date, rows: list[dict]) -> None:
    pd.DataFrame(rows).to_parquet(directory / f"{snapshot_date.isoformat()}.parquet")


if __name__ == "__main__":
    unittest.main()
