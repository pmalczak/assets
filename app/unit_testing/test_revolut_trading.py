# -*- coding: utf-8 -*-
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from evaluators.evaluate_broker_revolut import evaluate_broker_revolut, open_holdings_at_cost
from importers.assets.data_model import AssetsDef, GroupDomain, KindDomain, TypeDomain
from importers.revolut.read_r_trading import (
    _read_revolut_trading_transactions,
    extract_statement_period,
    normalize_trading_transactions,
    parse_trading_pnl_csv,
    period_gap_warnings,
)
from importers.revolut.trading_data_model import RevolutTradingFile, RevolutTradingPnlFile
from maintenance.move_downloaded_results import ACTION_MOVED, ACTION_SKIPPED
from maintenance.move_revolut_files import broker_asset_id, move_revolut_files


def _trading_csv(path: Path, rows: list[dict]) -> None:
    cols = [
        RevolutTradingFile.DATE,
        RevolutTradingFile.TICKER,
        RevolutTradingFile.TYPE,
        RevolutTradingFile.QUANTITY,
        RevolutTradingFile.PRICE_PER_SHARE,
        RevolutTradingFile.TOTAL_AMOUNT,
        RevolutTradingFile.CURRENCY,
        RevolutTradingFile.FX_RATE,
    ]
    pd.DataFrame(rows, columns=cols).to_csv(path, index=False)


class PeriodHelpersTests(unittest.TestCase):
    def test_extract_period_standard(self):
        p = Path("trading-account-statement_2026-01-01_2026-07-15_pl-pl_00bfc5.csv")
        self.assertEqual(
            extract_statement_period(p, "trading-account-statement"),
            ("2026-01-01", "2026-07-15"),
        )

    def test_extract_period_with_suffix(self):
        p = Path("trading-pnl-statement_2026-07-01_2026-07-30_pl-pl_5f77f0_1.csv")
        self.assertEqual(
            extract_statement_period(p, "trading-pnl-statement"),
            ("2026-07-01", "2026-07-30"),
        )

    def test_gap_warning_when_periods_not_contiguous(self):
        warnings = period_gap_warnings(
            [("2025-11-01", "2025-11-30"), ("2026-01-01", "2026-01-31")],
            label="trading-account-statement",
        )
        self.assertEqual(len(warnings), 1)
        self.assertIn("2025-12-01", warnings[0])
        self.assertIn("2025-12-31", warnings[0])
        self.assertIn("możliwa utrata danych", warnings[0])

    def test_no_gap_when_overlapping_or_adjacent(self):
        warnings = period_gap_warnings(
            [
                ("2025-11-01", "2025-12-31"),
                ("2026-01-01", "2026-07-15"),
                ("2026-07-01", "2026-07-30"),
            ],
            label="trading-account-statement",
        )
        self.assertEqual(warnings, [])


class ParsePnlTests(unittest.TestCase):
    def test_parse_sections(self):
        text = """Income from Sells
Date acquired,Date sold,Symbol,Security name,ISIN,Country,Quantity,Cost basis,Gross proceeds,Gross PnL,Currency
2025-11-03,2026-03-17,AAA,Alpha ETF,IE00AAAAAAAA,EU,1.0,10,12,2,EUR

Other income & fees
Date,Symbol,Security name,ISIN,Country,Gross amount,Withholding tax,Net Amount,Currency
2025-12-01,AAA,Alpha ETF dividend,IE00AAAAAAAA,IE,1.5,$0,1.5 PLN,PLN
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trading-pnl-statement_2025-11-01_2025-12-31_pl-pl_x.csv"
            path.write_text(text, encoding="utf-8")
            df = parse_trading_pnl_csv(path)
        self.assertEqual(len(df), 2)
        sections = set(df[RevolutTradingPnlFile.SECTION])
        self.assertEqual(
            sections,
            {RevolutTradingPnlFile.SECTION_SELLS, RevolutTradingPnlFile.SECTION_OTHER},
        )
        sell = df[df[RevolutTradingPnlFile.SECTION] == RevolutTradingPnlFile.SECTION_SELLS].iloc[0]
        self.assertEqual(sell[RevolutTradingPnlFile.SYMBOL], "AAA")
        self.assertEqual(sell[RevolutTradingPnlFile.ISIN], "IE00AAAAAAAA")


class DedupeTradingTests(unittest.TestCase):
    def test_overlap_dedupes_exact_rows(self):
        shared = {
            RevolutTradingFile.DATE: "2026-07-02T10:00:00.000000Z",
            RevolutTradingFile.TICKER: "AAA",
            RevolutTradingFile.TYPE: RevolutTradingFile.TYPE_BUY,
            RevolutTradingFile.QUANTITY: 1.0,
            RevolutTradingFile.PRICE_PER_SHARE: "10",
            RevolutTradingFile.TOTAL_AMOUNT: "10",
            RevolutTradingFile.CURRENCY: "EUR",
            RevolutTradingFile.FX_RATE: 1.0,
        }
        unique_a = {
            **shared,
            RevolutTradingFile.DATE: "2026-06-01T10:00:00.000000Z",
            RevolutTradingFile.TICKER: "BBB",
        }
        unique_b = {
            **shared,
            RevolutTradingFile.DATE: "2026-07-20T10:00:00.000000Z",
            RevolutTradingFile.TICKER: "CCC",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _trading_csv(
                root / "trading-account-statement_2026-01-01_2026-07-15_pl-pl_a.csv",
                [unique_a, shared],
            )
            _trading_csv(
                root / "trading-account-statement_2026-07-01_2026-07-30_pl-pl_b.csv",
                [shared, unique_b],
            )
            df = _read_revolut_trading_transactions(root)
        self.assertEqual(len(df), 3)
        tickers = set(df[RevolutTradingFile.TICKER])
        self.assertEqual(tickers, {"AAA", "BBB", "CCC"})


class NormalizeTradingTests(unittest.TestCase):
    def test_sell_qty_negative_amounts_float_fx_inverted(self):
        raw = pd.DataFrame(
            [
                {
                    RevolutTradingFile.DATE: "2026-01-01T00:00:00Z",
                    RevolutTradingFile.TICKER: "AAA",
                    RevolutTradingFile.TYPE: RevolutTradingFile.TYPE_BUY,
                    RevolutTradingFile.QUANTITY: 1.5,
                    RevolutTradingFile.PRICE_PER_SHARE: "EUR 67.86",
                    RevolutTradingFile.TOTAL_AMOUNT: "EUR 125",
                    RevolutTradingFile.CURRENCY: "EUR",
                    RevolutTradingFile.FX_RATE: 0.2355,
                    RevolutTradingFile.FILE_DATE: "2026-01-31",
                    RevolutTradingFile.PERIOD_START: "2026-01-01",
                    RevolutTradingFile.PERIOD_END: "2026-01-31",
                },
                {
                    RevolutTradingFile.DATE: "2026-02-01T00:00:00Z",
                    RevolutTradingFile.TICKER: "AAA",
                    RevolutTradingFile.TYPE: RevolutTradingFile.TYPE_SELL,
                    RevolutTradingFile.QUANTITY: 0.5,
                    RevolutTradingFile.PRICE_PER_SHARE: "EUR 70.00",
                    RevolutTradingFile.TOTAL_AMOUNT: "EUR 35",
                    RevolutTradingFile.CURRENCY: "EUR",
                    RevolutTradingFile.FX_RATE: 0.25,
                    RevolutTradingFile.FILE_DATE: "2026-01-31",
                    RevolutTradingFile.PERIOD_START: "2026-01-01",
                    RevolutTradingFile.PERIOD_END: "2026-01-31",
                },
            ]
        )
        df = normalize_trading_transactions(raw)
        buy = df[df[RevolutTradingFile.TYPE] == RevolutTradingFile.TYPE_BUY].iloc[0]
        sell = df[df[RevolutTradingFile.TYPE] == RevolutTradingFile.TYPE_SELL].iloc[0]
        self.assertAlmostEqual(float(buy[RevolutTradingFile.QUANTITY]), 1.5)
        self.assertAlmostEqual(float(sell[RevolutTradingFile.QUANTITY]), -0.5)
        self.assertAlmostEqual(float(buy[RevolutTradingFile.PRICE_PER_SHARE]), 67.86)
        self.assertAlmostEqual(float(buy[RevolutTradingFile.TOTAL_AMOUNT]), -125.0)
        self.assertAlmostEqual(float(sell[RevolutTradingFile.TOTAL_AMOUNT]), 35.0)
        self.assertAlmostEqual(float(sell[RevolutTradingFile.PRICE_PER_SHARE]), 70.0)
        self.assertAlmostEqual(float(buy[RevolutTradingFile.FX_RATE]), 4.2463)  # 1/0.2355
        self.assertAlmostEqual(float(sell[RevolutTradingFile.FX_RATE]), 4.0)  # 1/0.25

    def test_read_applies_normalize(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _trading_csv(
                root / "trading-account-statement_2026-01-01_2026-01-31_pl-pl_a.csv",
                [
                    {
                        RevolutTradingFile.DATE: "2026-01-10T12:00:00Z",
                        RevolutTradingFile.TICKER: "AAA",
                        RevolutTradingFile.TYPE: RevolutTradingFile.TYPE_SELL,
                        RevolutTradingFile.QUANTITY: 2.0,
                        RevolutTradingFile.PRICE_PER_SHARE: "EUR 10.50",
                        RevolutTradingFile.TOTAL_AMOUNT: "EUR 21",
                        RevolutTradingFile.CURRENCY: "EUR",
                        RevolutTradingFile.FX_RATE: 0.5,
                    }
                ],
            )
            df = _read_revolut_trading_transactions(root)
        self.assertEqual(len(df), 1)
        self.assertAlmostEqual(float(df.iloc[0][RevolutTradingFile.QUANTITY]), -2.0)
        self.assertAlmostEqual(float(df.iloc[0][RevolutTradingFile.PRICE_PER_SHARE]), 10.5)
        self.assertAlmostEqual(float(df.iloc[0][RevolutTradingFile.TOTAL_AMOUNT]), 21.0)
        self.assertAlmostEqual(float(df.iloc[0][RevolutTradingFile.FX_RATE]), 2.0)


class OpenHoldingsCostTests(unittest.TestCase):
    def test_fifo_cost_not_last_sale_price(self):
        df = pd.DataFrame(
            [
                {
                    RevolutTradingFile.DATE: "2026-01-01T00:00:00Z",
                    RevolutTradingFile.TICKER: "AAA",
                    RevolutTradingFile.TYPE: RevolutTradingFile.TYPE_BUY,
                    RevolutTradingFile.QUANTITY: 2.0,
                    RevolutTradingFile.PRICE_PER_SHARE: "10",
                    RevolutTradingFile.TOTAL_AMOUNT: "20",
                    RevolutTradingFile.CURRENCY: "EUR",
                    RevolutTradingFile.FX_RATE: 1.0,
                },
                {
                    RevolutTradingFile.DATE: "2026-02-01T00:00:00Z",
                    RevolutTradingFile.TICKER: "AAA",
                    RevolutTradingFile.TYPE: RevolutTradingFile.TYPE_BUY,
                    RevolutTradingFile.QUANTITY: 1.0,
                    RevolutTradingFile.PRICE_PER_SHARE: "30",
                    RevolutTradingFile.TOTAL_AMOUNT: "30",
                    RevolutTradingFile.CURRENCY: "EUR",
                    RevolutTradingFile.FX_RATE: 1.0,
                },
                {
                    RevolutTradingFile.DATE: "2026-03-01T00:00:00Z",
                    RevolutTradingFile.TICKER: "AAA",
                    RevolutTradingFile.TYPE: RevolutTradingFile.TYPE_SELL,
                    RevolutTradingFile.QUANTITY: -1.0,
                    RevolutTradingFile.PRICE_PER_SHARE: 100.0,
                    RevolutTradingFile.TOTAL_AMOUNT: 100.0,
                    RevolutTradingFile.CURRENCY: "EUR",
                    RevolutTradingFile.FX_RATE: 1.0,
                },
            ]
        )
        holdings = open_holdings_at_cost(df)
        self.assertIn("AAA", holdings)
        # remaining: 1@10 + 1@30 = 40 (not marked at sale 100)
        self.assertAlmostEqual(holdings["AAA"]["qty"], 2.0)
        self.assertAlmostEqual(holdings["AAA"]["cost"], 40.0)

    def test_complete_history_no_negative(self):
        df = pd.DataFrame(
            [
                {
                    RevolutTradingFile.DATE: "2026-01-01T00:00:00Z",
                    RevolutTradingFile.TICKER: "AAA",
                    RevolutTradingFile.TYPE: RevolutTradingFile.TYPE_BUY,
                    RevolutTradingFile.QUANTITY: 1.5,
                    RevolutTradingFile.PRICE_PER_SHARE: "20",
                    RevolutTradingFile.TOTAL_AMOUNT: "30",
                    RevolutTradingFile.CURRENCY: "EUR",
                    RevolutTradingFile.FX_RATE: 1.0,
                },
                {
                    RevolutTradingFile.DATE: "2026-02-01T00:00:00Z",
                    RevolutTradingFile.TICKER: "AAA",
                    RevolutTradingFile.TYPE: RevolutTradingFile.TYPE_SELL,
                    RevolutTradingFile.QUANTITY: -1.5,
                    RevolutTradingFile.PRICE_PER_SHARE: 22.0,
                    RevolutTradingFile.TOTAL_AMOUNT: 33.0,
                    RevolutTradingFile.CURRENCY: "EUR",
                    RevolutTradingFile.FX_RATE: 1.0,
                },
            ]
        )
        self.assertEqual(open_holdings_at_cost(df), {})


class MoveRevolutDepositFilesTests(unittest.TestCase):
    def test_skips_non_uuid_export_as_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            download = home / "Dropbox" / "INWESTYCJE" / "download" / "pm"
            cash_pool = home / "Dropbox" / "INWESTYCJE" / "cash_pool"
            download.mkdir(parents=True)
            cash_pool.mkdir(parents=True)

            src = download / "Eksport transakcji.csv"
            src.write_text(
                '"datetime","date","type","amount","currency"\n'
                '"2026-07-22T15:01:38Z","2026-07-22","CUSTOMER_INPAYMENT","400","PLN"\n',
                encoding="utf-8",
            )

            with patch("pathlib.Path.home", return_value=home):
                results = move_revolut_files(cash_pool, "p_re", assets_root=home / "assets")

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].action, ACTION_SKIPPED)
            self.assertTrue(src.is_file())

    def test_moves_uuid_deposit_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            download = home / "Dropbox" / "INWESTYCJE" / "download" / "pm"
            cash_pool = home / "Dropbox" / "INWESTYCJE" / "cash_pool" / "p_re_eur"
            download.mkdir(parents=True)
            cash_pool.mkdir(parents=True)

            stem = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
            src = download / f"{stem}.csv"
            src.write_text(
                "Completed Date,Product name,Description,Money out,Money in,Balance\n"
                "01 Jan 2026,Flexible Cash Funds EUR,Money carried forward,,,€100.00\n",
                encoding="utf-8",
            )

            with patch("pathlib.Path.home", return_value=home):
                results = move_revolut_files(
                    home / "Dropbox" / "INWESTYCJE" / "cash_pool",
                    "p_re",
                    assets_root=home / "assets",
                )

            moved = [r for r in results if r.action == ACTION_MOVED]
            self.assertEqual(len(moved), 1)
            self.assertFalse(src.exists())
            self.assertTrue((cash_pool / f"{stem}.csv").is_file())


class MoveTradingFilesTests(unittest.TestCase):
    def test_moves_trading_to_assets_robo(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            download = home / "Dropbox" / "INWESTYCJE" / "download" / "pm"
            assets = home / "Dropbox" / "INWESTYCJE" / "assets"
            cash_pool = home / "Dropbox" / "INWESTYCJE" / "cash_pool"
            download.mkdir(parents=True)
            assets.mkdir(parents=True)
            cash_pool.mkdir(parents=True)

            src = download / "trading-account-statement_2026-01-01_2026-01-31_pl-pl_x.csv"
            _trading_csv(
                src,
                [
                    {
                        RevolutTradingFile.DATE: "2026-01-02T00:00:00Z",
                        RevolutTradingFile.TICKER: "AAA",
                        RevolutTradingFile.TYPE: RevolutTradingFile.TYPE_BUY,
                        RevolutTradingFile.QUANTITY: 1.0,
                        RevolutTradingFile.PRICE_PER_SHARE: "10",
                        RevolutTradingFile.TOTAL_AMOUNT: "10",
                        RevolutTradingFile.CURRENCY: "EUR",
                        RevolutTradingFile.FX_RATE: 1.0,
                    }
                ],
            )
            pnl = download / "trading-pnl-statement_2026-01-01_2026-01-31_pl-pl_y.csv"
            pnl.write_text(
                "Income from Sells\n"
                "Date acquired,Date sold,Symbol,Security name,ISIN,Country,"
                "Quantity,Cost basis,Gross proceeds,Gross PnL,Currency\n",
                encoding="utf-8",
            )

            with patch("pathlib.Path.home", return_value=home):
                results = move_revolut_files(cash_pool, "p_re", assets_root=assets)

            moved = [r for r in results if r.action == ACTION_MOVED]
            self.assertEqual(len(moved), 1)  # pnl empty (no data rows) deleted
            dest = assets / broker_asset_id("p_re") / src.name
            self.assertTrue(dest.is_file())
            self.assertFalse(src.exists())


class EvaluateBrokerTests(unittest.TestCase):
    def test_evaluate_synthetic_single_row_sum_of_costs(self):
        trading = pd.DataFrame(
            [
                {
                    RevolutTradingFile.DATE: "2026-01-01T00:00:00Z",
                    RevolutTradingFile.TICKER: "AAA",
                    RevolutTradingFile.TYPE: RevolutTradingFile.TYPE_BUY,
                    RevolutTradingFile.QUANTITY: 2.0,
                    RevolutTradingFile.PRICE_PER_SHARE: "10.5",
                    RevolutTradingFile.TOTAL_AMOUNT: "21",
                    RevolutTradingFile.CURRENCY: "EUR",
                    RevolutTradingFile.FX_RATE: 1.0,
                    RevolutTradingFile.FILE_DATE: "2026-01-31",
                    RevolutTradingFile.PERIOD_START: "2026-01-01",
                    RevolutTradingFile.PERIOD_END: "2026-01-31",
                },
                {
                    RevolutTradingFile.DATE: "2026-01-02T00:00:00Z",
                    RevolutTradingFile.TICKER: "BBB",
                    RevolutTradingFile.TYPE: RevolutTradingFile.TYPE_BUY,
                    RevolutTradingFile.QUANTITY: 1.0,
                    RevolutTradingFile.PRICE_PER_SHARE: "30",
                    RevolutTradingFile.TOTAL_AMOUNT: "30",
                    RevolutTradingFile.CURRENCY: "EUR",
                    RevolutTradingFile.FX_RATE: 1.0,
                    RevolutTradingFile.FILE_DATE: "2026-01-31",
                    RevolutTradingFile.PERIOD_START: "2026-01-01",
                    RevolutTradingFile.PERIOD_END: "2026-01-31",
                },
            ]
        )
        catalog = pd.Series(
            {
                AssetsDef.ID: "p_re_robo",
                AssetsDef.TYPE: TypeDomain.EQUITIES,
                AssetsDef.GROUP: GroupDomain.INVESTMENT,
                AssetsDef.DESCR: "revolut robo",
                AssetsDef.KIND: KindDomain.BROKER,
                AssetsDef.CURRENCY: "EUR",
                AssetsDef.NOTES: "",
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "p_re_robo").mkdir()
            with (
                patch(
                    "evaluators.evaluate_broker_revolut.read_revolut_trading_transactions",
                    return_value=(trading, []),
                ),
                patch(
                    "evaluators.evaluate_broker_revolut.read_revolut_trading_pnl",
                    return_value=(pd.DataFrame(), ["luka test"]),
                ),
                patch(
                    "evaluators.evaluate_broker_revolut.resolve_asset_dir",
                    return_value=root / "p_re_robo",
                ),
            ):
                result, warnings = evaluate_broker_revolut(
                    root, "p_re_robo", catalog, date(2026, 1, 31)
                )

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0][AssetsDef.ID], "p_re_robo")
        self.assertAlmostEqual(float(result.iloc[0][AssetsDef.VALUE]), 51.0)
        self.assertEqual(result.iloc[0][AssetsDef.TYPE], TypeDomain.EQUITIES)
        self.assertEqual(result.iloc[0][AssetsDef.GROUP], GroupDomain.INVESTMENT)
        self.assertEqual(result.iloc[0][AssetsDef.DESCR], "revolut robo (2 poz.)")
        self.assertEqual(warnings, ["luka test"])


if __name__ == "__main__":
    unittest.main()
