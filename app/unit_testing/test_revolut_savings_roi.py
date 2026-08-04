# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from importers.revolut.deposit_data_model import RevolutDepositFile
from importers.revolut.read_r_deposits import _read_revolut_deposit_transactions
from importers.revolut.savings_statement import (
    OPIS_DEPOSIT,
    OPIS_INTEREST,
    OPIS_WITHDRAWAL,
    assert_no_coverage_gaps,
    detect_savings_currency,
    empty_savings_frame,
    normalize_savings_statement,
    parse_savings_period,
)
from maintenance.move_downloaded_results import ACTION_MOVED
from maintenance.move_revolut_files import move_revolut_files
from roi.categories import CAPEX, DIVESTMENT, OPEX
from roi.data_model import CashFlowEvent
from roi.revolut_deposit_roi import (
    build_deposit_cashflows,
    build_tax_liability_cashflows,
    compute_revolut_deposit_roi,
    latest_deposit_balance,
    tax_liability_asset_id,
    tax_liability_value,
)


def _savings_csv_text(rows: list[str]) -> str:
    header = "Data,Opis,Wypłata pieniędzy,Wpływy,Saldo\n"
    return header + "\n".join(rows) + "\n"


class SavingsStatementParseTests(unittest.TestCase):
    def test_parse_period_and_currency_eur(self):
        path = Path("savings-statement_2025-10-01_2026-05-15_pl-pl_1244305841_x.csv")
        self.assertEqual(parse_savings_period(path), (date(2025, 10, 1), date(2026, 5, 15)))
        raw = pd.DataFrame(
            {
                "Data": ["5 paź 2025"],
                "Opis": [OPIS_DEPOSIT],
                "Wypłata pieniędzy": [""],
                "Wpływy": ["100,00€"],
                "Saldo": ["100,00€"],
            }
        )
        self.assertEqual(detect_savings_currency(raw), "eur")

    def test_parse_currency_pln(self):
        raw = pd.DataFrame(
            {
                "Data": ["20 sie 2025"],
                "Opis": [OPIS_DEPOSIT],
                "Wypłata pieniędzy": [""],
                "Wpływy": ["100,00 PLN"],
                "Saldo": ["100,00 PLN"],
            }
        )
        self.assertEqual(detect_savings_currency(raw), "pln")

    def test_normalize_amounts_and_dates(self):
        raw = pd.DataFrame(
            {
                "Data": ["20 sie 2025", "1 sty 2026", "5 lis 2025"],
                "Opis": [OPIS_DEPOSIT, OPIS_INTEREST, OPIS_WITHDRAWAL],
                "Wypłata pieniędzy": ["", "", "100,00 PLN"],
                "Wpływy": ["100,00 PLN", "7,45 PLN", ""],
                "Saldo": ["100,00 PLN", "107,45 PLN", "0,85 PLN"],
            }
        )
        df = normalize_savings_statement(
            raw, period_start=date(2025, 8, 1), period_end=date(2026, 1, 31)
        )
        self.assertEqual(len(df), 3)
        by_date = df.set_index(RevolutDepositFile.DATE)
        self.assertEqual(by_date.loc["2025-08-20"][RevolutDepositFile.CURRENCY], "pln")
        self.assertAlmostEqual(float(by_date.loc["2025-08-20"][RevolutDepositFile.MONEY_IN]), 100.0)
        self.assertAlmostEqual(float(by_date.loc["2026-01-01"][RevolutDepositFile.MONEY_IN]), 7.45)
        self.assertAlmostEqual(float(by_date.loc["2025-11-05"][RevolutDepositFile.MONEY_OUT]), 100.0)

    def test_coverage_gap_raises(self):
        with self.assertRaises(ValueError) as ctx:
            assert_no_coverage_gaps(
                [(date(2025, 1, 1), date(2025, 1, 31)), (date(2025, 3, 1), date(2025, 3, 31))],
                asset_id="p_re_eur",
            )
        self.assertIn("Luka", str(ctx.exception))

    def test_adjacent_periods_ok(self):
        assert_no_coverage_gaps(
            [(date(2025, 1, 1), date(2025, 1, 31)), (date(2025, 2, 1), date(2025, 2, 28))]
        )

    def test_empty_frame_has_unique_expected_columns(self):
        df = empty_savings_frame()
        self.assertFalse(df.columns.duplicated().any())
        self.assertEqual(set(df.columns), RevolutDepositFile.expected_columns())


class MoveSavingsStatementTests(unittest.TestCase):
    def test_moves_savings_to_currency_folder_from_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            download = home / "Dropbox" / "INWESTYCJE" / "download" / "pm"
            cash_pool = home / "Dropbox" / "INWESTYCJE" / "cash_pool"
            download.mkdir(parents=True)
            cash_pool.mkdir(parents=True)

            src = download / "savings-statement_2025-08-01_2025-12-31_pl-pl_1330814470_x.csv"
            src.write_text(
                _savings_csv_text(
                    [
                        '20 sie 2025,Depozyt,,"100,00 PLN","100,00 PLN"',
                    ]
                ),
                encoding="utf-8",
            )

            with patch("pathlib.Path.home", return_value=home):
                results = move_revolut_files(cash_pool, "p_re", assets_root=home / "assets")

            moved = [r for r in results if r.action == ACTION_MOVED]
            self.assertEqual(len(moved), 1)
            self.assertFalse(src.exists())
            self.assertTrue(
                (cash_pool / "p_re_pln" / src.name).is_file()
            )


class DepositCashflowTests(unittest.TestCase):
    def _sample_df(self) -> pd.DataFrame:
        raw = pd.DataFrame(
            {
                "Data": ["20 sie 2025", "1 sty 2026", "5 lis 2025"],
                "Opis": [OPIS_DEPOSIT, OPIS_INTEREST, OPIS_WITHDRAWAL],
                "Wypłata pieniędzy": ["", "", "50,00€"],
                "Wpływy": ["1000,00€", "10,00€", ""],
                "Saldo": ["1000,00€", "1010,00€", "960,00€"],
            }
        )
        return normalize_savings_statement(
            raw, period_start=date(2025, 8, 1), period_end=date(2026, 1, 31)
        )

    def test_cashflow_signs(self):
        df = self._sample_df()
        cf = build_deposit_cashflows(df, "p_re_eur")
        cats = cf[CashFlowEvent.CATEGORY].tolist()
        self.assertNotIn("REVENUES", cats)
        by_cat = {
            row[CashFlowEvent.CATEGORY]: row[CashFlowEvent.AMOUNT]
            for _, row in cf.iterrows()
        }
        self.assertAlmostEqual(by_cat[CAPEX], -1000.0)
        self.assertAlmostEqual(by_cat[DIVESTMENT], 50.0)
        self.assertEqual(len(cf), 2)

    def test_tax_only_current_year(self):
        df = self._sample_df()
        # dodaj odsetki 2025 — nie powinny wejść do tax 2026
        extra = normalize_savings_statement(
            pd.DataFrame(
                {
                    "Data": ["10 gru 2025"],
                    "Opis": [OPIS_INTEREST],
                    "Wypłata pieniędzy": [""],
                    "Wpływy": ["5,00€"],
                    "Saldo": ["1015,00€"],
                }
            ),
            period_start=date(2025, 8, 1),
            period_end=date(2026, 1, 31),
        )
        df = pd.concat([df, extra], ignore_index=True)
        tax_cf = build_tax_liability_cashflows(df, "p_re_eur", 2026)
        self.assertEqual(len(tax_cf), 1)
        self.assertEqual(tax_cf.iloc[0][CashFlowEvent.CATEGORY], OPEX)
        self.assertAlmostEqual(tax_cf.iloc[0][CashFlowEvent.AMOUNT], -1.9)
        self.assertEqual(
            tax_cf.iloc[0][CashFlowEvent.ASSET_ID],
            tax_liability_asset_id("p_re_eur", 2026),
        )

    def test_terminal_last_balance(self):
        df = self._sample_df()
        self.assertAlmostEqual(latest_deposit_balance(df, date(2025, 11, 5)), 960.0)
        self.assertAlmostEqual(latest_deposit_balance(df, date(2025, 8, 20)), 1000.0)

    def test_tax_liability_value(self):
        df = self._sample_df()
        self.assertAlmostEqual(tax_liability_value(df, date(2026, 1, 15)), -1.9)


class ReadSavingsWithGapTests(unittest.TestCase):
    def test_read_raises_on_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            f1 = root / "savings-statement_2025-01-01_2025-01-31_pl-pl_1_x.csv"
            f2 = root / "savings-statement_2025-03-01_2025-03-31_pl-pl_1_x.csv"
            body = _savings_csv_text(['15 sty 2025,Depozyt,,"10,00€","10,00€"'])
            f1.write_text(body, encoding="utf-8")
            f2.write_text(
                _savings_csv_text(['15 mar 2025,Depozyt,,"10,00€","20,00€"']),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                _read_revolut_deposit_transactions(root, asset_id="p_re_eur")


class ComputeDepositRoiIntegrationTests(unittest.TestCase):
    def test_compute_from_cash_pool_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asset_dir = root / "p_re_eur"
            asset_dir.mkdir()
            src = asset_dir / "savings-statement_2025-08-01_2026-01-31_pl-pl_1_x.csv"
            src.write_text(
                _savings_csv_text(
                    [
                        '20 sie 2025,Depozyt,,"1000,00€","1000,00€"',
                        '1 sty 2026,Oprocentowanie brutto,,"10,00€","1010,00€"',
                    ]
                ),
                encoding="utf-8",
            )

            with patch(
                "roi.revolut_deposit_roi.read_revolut_deposit_transactions",
                side_effect=lambda path, asset_id: _read_revolut_deposit_transactions(
                    path, asset_id=asset_id
                ),
            ):
                summary, events, warnings = compute_revolut_deposit_roi(
                    date(2026, 1, 15),
                    cash_pool_root=root,
                    asset_ids=("p_re_eur",),
                )

            self.assertEqual(warnings, [])
            self.assertEqual(len(summary), 2)  # deposit + tax
            deposit = summary[summary["asset_id"] == "p_re_eur"].iloc[0]
            self.assertAlmostEqual(float(deposit["capex"]), -1000)
            self.assertAlmostEqual(float(deposit["revenue"]), 0)
            self.assertAlmostEqual(float(deposit["terminal_unrealized"]), 1010)
            tax_id = tax_liability_asset_id("p_re_eur", 2026)
            self.assertIn(tax_id, events)
            self.assertIn("p_re_eur", events)


if __name__ == "__main__":
    unittest.main()
