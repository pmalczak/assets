# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

from importers.degiro.data_model import (
    ACCOUNT_SOURCE,
    DEFAULT_DEGIRO_ASSET_ID,
    PORTFOLIO_SOURCE,
    TRANSACTIONS_SOURCE,
    DegiroPortfolioFile,
)
from importers.degiro.read_degiro import (
    dated_filename,
    latest_portfolio_as_of,
    parse_degiro_number,
    period_from_account_file,
    read_account_csv,
    read_portfolio_csv,
    read_transactions_csv,
    _read_degiro_portfolio,
)
from maintenance.move_degiro_files import move_degiro_files
from maintenance.move_downloaded_results import ACTION_MOVED, ACTION_SKIPPED, KIND_DEGIRO
from roi.categories import CAPEX, REVENUES
from roi.data_model import CashFlowEvent
from roi.degiro_roi import compute_degiro_ticker_roi


PORTFOLIO = """Produkt,Symbol/ISIN,Suma,Kurs,Lokalna wartość,,Wartość w EUR
CASH & CASH FUND & FTX CASH (EUR),,,,EUR,"30,12","30,12"
INTER RAO LIETUVA AB,LT0000128621,150,"11,54",PLN,"1731,00","402,28"
"""

TRANSACTIONS = """Data,Czas,Produkt,ISIN,Giełda referencyjna,Miejsce wykonania,Liczba,Kurs,,Wartość lokalna,,Wartość EUR,Kurs wymiany,Opłaty AutoFX,Opłata transakcyjna DEGIRO i/lub opłata stron,Razem EUR,Identyfikator zlecenia
28-07-2021,09:41,INTER RAO LIETUVA AB,LT0000128621,WSE,XWAR,150,"19,5000",PLN,"-2925,00",PLN,"-635,97","4,5993","0,00","-0,79","-636,76",order-1
"""

ACCOUNT = """Data,Czas,Data,Produkt,ISIN,Opis,Kurs,Zmiana,,Saldo,,Identyfikator zlecenia
09-10-2025,02:01,30-09-2025,,,Flatex Interest Income,,EUR,"0,00",EUR,"30,12",
28-07-2021,09:42,28-07-2021,INTER RAO LIETUVA AB,LT0000128621,"Kupno 150 Inter RAO Lietuva AB@19,5 PLN (LT0000128621)",,EUR,"-635,97",EUR,"30,12",order-1
01-09-2021,10:00,01-09-2021,INTER RAO LIETUVA AB,LT0000128621,Dywidenda,,EUR,"5,00",EUR,"35,12",
"""


def _write_package(root: Path) -> None:
    (root / PORTFOLIO_SOURCE).write_text(PORTFOLIO, encoding="utf-8")
    (root / TRANSACTIONS_SOURCE).write_text(TRANSACTIONS, encoding="utf-8")
    (root / ACCOUNT_SOURCE).write_text(ACCOUNT, encoding="utf-8")


class DegiroReadTests(unittest.TestCase):
    def test_parse_number_and_account_period(self):
        self.assertAlmostEqual(parse_degiro_number("1 731,00"), 1731.0)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_package(root)
            self.assertEqual(
                period_from_account_file(root / ACCOUNT_SOURCE),
                (date(2021, 7, 28), date(2025, 10, 9)),
            )

    def test_read_export_shapes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_package(root)
            portfolio = read_portfolio_csv(root / PORTFOLIO_SOURCE)
            transactions = read_transactions_csv(root / TRANSACTIONS_SOURCE)
            account = read_account_csv(root / ACCOUNT_SOURCE)
            self.assertEqual(len(portfolio), 2)
            self.assertEqual(len(transactions), 1)
            self.assertEqual(len(account), 3)
            self.assertAlmostEqual(float(portfolio["Wartość w EUR"].sum()), 432.40)
            self.assertAlmostEqual(float(transactions.iloc[0]["Wartość EUR"]), -635.97)

    def test_overlapping_packages_same_end_do_not_double_portfolio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            long_start, short_start, end = date(2026, 1, 8), date(2026, 8, 13), date(2026, 8, 17)
            (root / dated_filename("portfolio", long_start, end)).write_text(PORTFOLIO, encoding="utf-8")
            (root / dated_filename("portfolio", short_start, end)).write_text(PORTFOLIO, encoding="utf-8")

            combined = _read_degiro_portfolio(root)
            latest = latest_portfolio_as_of(combined, date(2026, 8, 20))
            isin = latest[DegiroPortfolioFile.ISIN]
            has_isin = isin.notna() & isin.astype(str).str.strip().ne("")
            positions = latest.loc[has_isin]
            cash = latest.loc[~has_isin]

            self.assertEqual(len(combined), 2)
            self.assertEqual(len(positions), 1)
            self.assertEqual(len(cash), 1)
            self.assertAlmostEqual(float(positions.iloc[0][DegiroPortfolioFile.VALUE_EUR]), 402.28)
            self.assertAlmostEqual(float(latest[DegiroPortfolioFile.VALUE_EUR].sum()), 432.40)
            self.assertEqual(str(latest[DegiroPortfolioFile.PERIOD_START].iloc[0]), short_start.isoformat())


class MoveDegiroTests(unittest.TestCase):
    def test_moves_package_and_renames_from_account_period(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            download = home / "Downloads"
            assets = home / "assets"
            download.mkdir()
            assets.mkdir()
            _write_package(download)

            results = move_degiro_files(assets, download)
            self.assertEqual(len(results), 3)
            self.assertTrue(all(r.action == ACTION_MOVED for r in results))
            self.assertTrue(all(r.kind == KIND_DEGIRO for r in results))
            target_dir = assets / DEFAULT_DEGIRO_ASSET_ID
            self.assertTrue((target_dir / dated_filename("portfolio", date(2021, 7, 28), date(2025, 10, 9))).is_file())
            self.assertFalse((download / ACCOUNT_SOURCE).is_file())

    def test_existing_covering_package_skips_incoming(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            download = root / "Downloads"
            assets = root / "assets"
            target = assets / DEFAULT_DEGIRO_ASSET_ID
            download.mkdir()
            target.mkdir(parents=True)
            _write_package(download)
            start, end = date(2021, 7, 28), date(2025, 10, 9)
            (target / dated_filename("portfolio", start, end)).write_text(PORTFOLIO, encoding="utf-8")
            (target / dated_filename("transactions", start, end)).write_text(TRANSACTIONS, encoding="utf-8")
            (target / dated_filename("account", start, end)).write_text(ACCOUNT, encoding="utf-8")

            results = move_degiro_files(assets, download)
            self.assertTrue(all(r.action == ACTION_SKIPPED for r in results))
            self.assertFalse((download / PORTFOLIO_SOURCE).is_file())


class DegiroRoiTests(unittest.TestCase):
    def test_compute_roi_from_transactions_dividend_and_portfolio_terminal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start, end = date(2021, 7, 28), date(2025, 10, 9)
            (root / dated_filename("portfolio", start, end)).write_text(PORTFOLIO, encoding="utf-8")
            (root / dated_filename("transactions", start, end)).write_text(TRANSACTIONS, encoding="utf-8")
            (root / dated_filename("account", start, end)).write_text(ACCOUNT, encoding="utf-8")

            portfolio = pd.concat([read_portfolio_csv(root / dated_filename("portfolio", start, end))])
            transactions = pd.concat([read_transactions_csv(root / dated_filename("transactions", start, end))])
            account = pd.concat([read_account_csv(root / dated_filename("account", start, end))])
            for df in (portfolio, transactions, account):
                df["period_start"] = start.isoformat()
                df["period_end"] = end.isoformat()
                df["ref_date"] = end.isoformat()

            summary, events, warnings = compute_degiro_ticker_roi(
                date(2026, 1, 1),
                portfolio_df=portfolio,
                transactions_df=transactions,
                account_df=account,
            )
            self.assertEqual(warnings, [])
            self.assertEqual(len(summary), 1)
            row = summary.iloc[0]
            self.assertEqual(row["asset_id"], "p_degiro:LT0000128621")
            self.assertFalse(bool(row["is_sold"]))
            self.assertAlmostEqual(float(row["capex"]), -636.0)
            self.assertAlmostEqual(float(row["revenue"]), 5.0)
            self.assertAlmostEqual(float(row["terminal_unrealized"]), 402.0)
            self.assertAlmostEqual(float(row["roi_nominal"]), -229.0)
            cats = events["p_degiro:LT0000128621"][CashFlowEvent.CATEGORY].tolist()
            self.assertEqual(cats, [CAPEX, REVENUES])

    def test_roi_terminal_not_doubled_when_two_portfolios_share_period_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            long_start, short_start, end = date(2026, 1, 8), date(2026, 8, 13), date(2026, 8, 17)
            frames = []
            for start in (long_start, short_start):
                path = root / dated_filename("portfolio", start, end)
                path.write_text(PORTFOLIO, encoding="utf-8")
                df = read_portfolio_csv(path)
                df["period_start"] = start.isoformat()
                df["period_end"] = end.isoformat()
                df["ref_date"] = end.isoformat()
                frames.append(df)
            portfolio = pd.concat(frames, ignore_index=True)

            tx_path = root / dated_filename("transactions", long_start, end)
            acc_path = root / dated_filename("account", long_start, end)
            tx_path.write_text(TRANSACTIONS, encoding="utf-8")
            acc_path.write_text(ACCOUNT, encoding="utf-8")
            transactions = read_transactions_csv(tx_path)
            account = read_account_csv(acc_path)
            for df in (transactions, account):
                df["period_start"] = long_start.isoformat()
                df["period_end"] = end.isoformat()
                df["ref_date"] = end.isoformat()

            summary, _, warnings = compute_degiro_ticker_roi(
                date(2026, 8, 20),
                portfolio_df=portfolio,
                transactions_df=transactions,
                account_df=account,
            )
            self.assertEqual(warnings, [])
            self.assertEqual(len(summary), 1)
            self.assertAlmostEqual(float(summary.iloc[0]["terminal_unrealized"]), 402.0)
            self.assertAlmostEqual(float(summary.iloc[0]["capex"]), -636.0)


if __name__ == "__main__":
    unittest.main()
