# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from io import StringIO

from evaluators.evaluate_broker_traderepublic import (
    evaluate_broker_traderepublic,
    is_traderepublic_broker,
)
from importers.assets.data_model import AssetsDef, GroupDomain, KindDomain, TypeDomain
from importers.traderepublic.data_model import (
    DEFAULT_TRADEREPUBLIC_ASSET_ID,
    TradeRepublicFile,
)
from importers.traderepublic.read_traderepublic import (
    _read_traderepublic_transactions,
    dated_export_filename,
    extract_export_period,
    period_from_dataframe,
)
from importers.statement_download_date import download_date_of
from maintenance.move_downloaded_results import (
    ACTION_MOVED,
    ACTION_SKIPPED,
    KIND_TRADEREPUBLIC,
)
from maintenance.move_traderepublic_files import move_traderepublic_files
from move_dowloaded import run_move_downloaded
from roi.categories import CAPEX
from roi.data_model import CashFlowEvent
from roi.traderepublic_deposit_roi import (
    build_traderepublic_cashflows,
    compute_traderepublic_roi,
    nav_as_of,
)
from roi.xirr import cashflows_for_xirr, compute_xirr


_HEADER = (
    "datetime,date,account_type,category,type,asset_class,name,symbol,shares,price,"
    "amount,fee,tax,currency,original_amount,original_currency,fx_rate,description,"
    "transaction_id,counterparty_name,counterparty_iban,payment_reference,mcc_code"
)


def _row(
    *,
    tx_date: str,
    tx_id: str,
    tx_type: str = "CUSTOMER_INPAYMENT",
    amount: str = "400.000000",
    fee: str = "",
    tax: str = "",
    currency: str = "PLN",
    description: str = "Card Top up",
) -> str:
    return (
        f'"{tx_date}T15:01:38.075386Z","{tx_date}","DEFAULT","CASH","{tx_type}",'
        f'"","Piotr","","","","{amount}","{fee}","{tax}","{currency}","","","",'
        f'"{description}","{tx_id}","Piotr","","",""'
    )


def _sample_deposit_rows() -> list[str]:
    """Realistyczna próbka: top-up + 2× INTEREST_PAYMENT z Belką w tax."""
    return [
        _row(
            tx_date="2026-07-22",
            tx_id="tx-in",
            amount="400.000000",
            description="Card Top up with ****8959",
        ),
        _row(
            tx_date="2026-09-01",
            tx_id="tx-int-1",
            tx_type="INTEREST_PAYMENT",
            amount="1.640000",
            tax="-0.31",
            description="Interest payment for payout collection 1",
        ),
        _row(
            tx_date="2026-10-01",
            tx_id="tx-int-2",
            tx_type="INTEREST_PAYMENT",
            amount="1.980000",
            tax="-0.37",
            description="Interest payment for payout collection 2",
        ),
    ]


def _csv(rows: list[str]) -> str:
    return _HEADER + "\n" + "\n".join(rows) + "\n"


class TradeRepublicNamingTests(unittest.TestCase):
    def test_period_from_dataframe_and_filename(self):
        df = pd.read_csv(
            StringIO(
                _csv(
                    [
                        _row(tx_date="2026-07-22", tx_id="a"),
                        _row(tx_date="2026-08-01", tx_id="b"),
                    ]
                )
            )
        )
        start, end = period_from_dataframe(df)
        self.assertEqual((start, end), (date(2026, 7, 22), date(2026, 8, 1)))
        self.assertEqual(
            dated_export_filename(start, end),
            "eksport-transakcji_2026-07-22_2026-08-01.csv",
        )

    def test_extract_export_period(self):
        path = Path("eksport-transakcji_2026-01-01_2026-03-15.csv")
        self.assertEqual(
            extract_export_period(path),
            (date(2026, 1, 1), date(2026, 3, 15)),
        )


class MoveTradeRepublicTests(unittest.TestCase):
    def test_moves_and_renames_by_transaction_dates(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            download = home / "Dropbox" / "INWESTYCJE" / "download" / "pm"
            assets = home / "Dropbox" / "INWESTYCJE" / "assets"
            download.mkdir(parents=True)
            assets.mkdir(parents=True)

            src = download / "Eksport transakcji.csv"
            src.write_text(
                _csv([_row(tx_date="2026-07-22", tx_id="019f8a58-b89b-73d5-bef0-8fbaa2ef5da9")]),
                encoding="utf-8",
            )
            fetched = download_date_of(src)

            results = move_traderepublic_files(assets, download_dir=download)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].action, ACTION_MOVED)
            self.assertEqual(results[0].kind, KIND_TRADEREPUBLIC)
            target = (
                assets
                / DEFAULT_TRADEREPUBLIC_ASSET_ID
                / dated_export_filename(date(2026, 7, 22), date(2026, 7, 22), fetched)
            )
            self.assertTrue(target.is_file())
            self.assertFalse(src.is_file())

    def test_run_move_downloaded_takes_tr_before_revolut_skip(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            download = home / "Dropbox" / "INWESTYCJE" / "download" / "pm"
            gm = home / "Dropbox" / "INWESTYCJE" / "download" / "gm"
            assets = home / "Dropbox" / "INWESTYCJE" / "assets"
            cash_pool = home / "Dropbox" / "INWESTYCJE" / "cash_pool"
            downloads = home / "Downloads"
            for path in (download, gm, assets, cash_pool, downloads):
                path.mkdir(parents=True)

            src = download / "Eksport transakcji.csv"
            src.write_text(
                _csv([_row(tx_date="2026-07-22", tx_id="tx-1")]),
                encoding="utf-8",
            )

            with patch("pathlib.Path.home", return_value=home):
                results = run_move_downloaded(assets_root=assets, cash_pool_root=cash_pool)

            tr = [r for r in results if r.kind == KIND_TRADEREPUBLIC]
            self.assertEqual(len(tr), 1)
            self.assertEqual(tr[0].action, ACTION_MOVED)
            self.assertFalse(src.is_file())

    def test_skips_when_existing_same_period_covers_incoming(self):
        with tempfile.TemporaryDirectory() as tmp:
            assets = Path(tmp) / "assets"
            download = Path(tmp) / "download"
            target_dir = assets / DEFAULT_TRADEREPUBLIC_ASSET_ID
            target_dir.mkdir(parents=True)
            download.mkdir(parents=True)

            # Ten sam zakres dat w nazwie (min=max=2026-07-22) — incoming ⊆ existing.
            content = _csv(
                [
                    _row(tx_date="2026-07-22", tx_id="tx-1"),
                    _row(tx_date="2026-07-22", tx_id="tx-2"),
                ]
            )
            existing = target_dir / "eksport-transakcji_2026-07-22_2026-07-22.csv"
            existing.write_text(content, encoding="utf-8")

            src = download / "Eksport transakcji.csv"
            src.write_text(
                _csv([_row(tx_date="2026-07-22", tx_id="tx-1")]),
                encoding="utf-8",
            )

            results = move_traderepublic_files(assets, download_dir=download)
            self.assertEqual(results[0].action, ACTION_SKIPPED)
            self.assertFalse(src.is_file())
            self.assertTrue(existing.is_file())


class ReadTradeRepublicTests(unittest.TestCase):
    def test_gap_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "eksport-transakcji_2026-01-01_2026-01-10.csv").write_text(
                _csv([_row(tx_date="2026-01-01", tx_id="a"), _row(tx_date="2026-01-10", tx_id="b")]),
                encoding="utf-8",
            )
            (root / "eksport-transakcji_2026-01-20_2026-01-25.csv").write_text(
                _csv([_row(tx_date="2026-01-20", tx_id="c"), _row(tx_date="2026-01-25", tx_id="d")]),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError) as ctx:
                _read_traderepublic_transactions(root)
            self.assertIn("Luka w pokryciu", str(ctx.exception))

    def test_overlap_dedupes_by_transaction_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "eksport-transakcji_2026-01-01_2026-01-15.csv").write_text(
                _csv(
                    [
                        _row(tx_date="2026-01-01", tx_id="shared"),
                        _row(tx_date="2026-01-10", tx_id="only-a"),
                    ]
                ),
                encoding="utf-8",
            )
            (root / "eksport-transakcji_2026-01-10_2026-01-20.csv").write_text(
                _csv(
                    [
                        _row(tx_date="2026-01-10", tx_id="shared"),
                        _row(tx_date="2026-01-20", tx_id="only-b"),
                    ]
                ),
                encoding="utf-8",
            )
            df = _read_traderepublic_transactions(root)
            self.assertEqual(len(df), 3)
            self.assertEqual(
                sorted(df[TradeRepublicFile.TRANSACTION_ID].astype(str).tolist()),
                ["only-a", "only-b", "shared"],
            )

    def test_read_single_topup_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "eksport-transakcji_2026-07-22_2026-07-22.csv").write_text(
                _csv(
                    [
                        _row(
                            tx_date="2026-07-22",
                            tx_id="019f8a58-b89b-73d5-bef0-8fbaa2ef5da9",
                            description="Card Top up with ****8959",
                        )
                    ]
                ),
                encoding="utf-8",
            )
            df = _read_traderepublic_transactions(root)
            self.assertEqual(len(df), 1)
            self.assertEqual(df.iloc[0][TradeRepublicFile.TYPE], "CUSTOMER_INPAYMENT")
            TradeRepublicFile.check_structure(df)


class EvaluateTradeRepublicTests(unittest.TestCase):
    def test_is_traderepublic_broker(self):
        row = pd.Series({AssetsDef.ID: DEFAULT_TRADEREPUBLIC_ASSET_ID})
        self.assertTrue(is_traderepublic_broker(row))
        self.assertFalse(is_traderepublic_broker(pd.Series({AssetsDef.ID: "p_re_robo"})))

    def _catalog_row(self) -> pd.Series:
        return pd.Series(
            {
                AssetsDef.ID: DEFAULT_TRADEREPUBLIC_ASSET_ID,
                AssetsDef.TYPE: TypeDomain.EQUITIES,
                AssetsDef.GROUP: GroupDomain.INVESTMENT,
                AssetsDef.DESCR: "Trade Republic",
                AssetsDef.KIND: KindDomain.BROKER,
                AssetsDef.CURRENCY: "PLN",
                AssetsDef.NOTES: "",
            }
        )

    def test_evaluate_returns_deposit_nav(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asset_dir = root / DEFAULT_TRADEREPUBLIC_ASSET_ID
            asset_dir.mkdir()
            (asset_dir / "eksport-transakcji_2026-07-22_2026-10-01.csv").write_text(
                _csv(_sample_deposit_rows()),
                encoding="utf-8",
            )
            with (
                patch(
                    "evaluators.evaluate_broker_traderepublic.resolve_asset_dir",
                    return_value=asset_dir,
                ),
                patch(
                    "evaluators.evaluate_broker_traderepublic.read_traderepublic_transactions",
                    side_effect=lambda path, _aid: _read_traderepublic_transactions(path),
                ),
            ):
                result, warnings = evaluate_broker_traderepublic(
                    root,
                    DEFAULT_TRADEREPUBLIC_ASSET_ID,
                    self._catalog_row(),
                    date(2026, 10, 18),
                )
            self.assertEqual(len(result), 1)
            self.assertAlmostEqual(float(result.iloc[0][AssetsDef.VALUE]), 402.94, places=2)
            self.assertEqual(result.iloc[0][AssetsDef.TYPE], TypeDomain.DEPOSIT)
            self.assertEqual(result.iloc[0][AssetsDef.GROUP], GroupDomain.DEPOSIT)
            self.assertFalse(any("niezaimplementowana" in w for w in warnings))

    def test_evaluate_missing_dir_warns_instead_of_raising(self):
        missing = Path("/tmp/definitely-missing-p_traderepublic")
        with patch(
            "evaluators.evaluate_broker_traderepublic.resolve_asset_dir",
            return_value=missing,
        ):
            result, warnings = evaluate_broker_traderepublic(
                Path("/tmp"),
                DEFAULT_TRADEREPUBLIC_ASSET_ID,
                self._catalog_row(),
                date(2026, 8, 8),
            )
        self.assertEqual(len(result), 1)
        self.assertEqual(float(result.iloc[0][AssetsDef.VALUE]), 0.0)
        self.assertTrue(any("Brak katalogu" in w for w in warnings))


class TradeRepublicDepositRoiTests(unittest.TestCase):
    def _blotter(self) -> pd.DataFrame:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "eksport-transakcji_2026-07-22_2026-10-01.csv").write_text(
                _csv(_sample_deposit_rows()),
                encoding="utf-8",
            )
            return _read_traderepublic_transactions(root)

    def test_nav_full_and_cutoff(self):
        blotter = self._blotter()
        nav, warnings = nav_as_of(blotter, date(2026, 10, 18))
        self.assertAlmostEqual(nav, 402.94, places=2)
        self.assertEqual(warnings, [])

        nav_cut, _ = nav_as_of(blotter, date(2026, 9, 15))
        self.assertAlmostEqual(nav_cut, 401.33, places=2)

    def test_cashflows_capex_only_no_interest(self):
        blotter = self._blotter()
        cf, warnings = build_traderepublic_cashflows(
            blotter, DEFAULT_TRADEREPUBLIC_ASSET_ID
        )
        self.assertEqual(warnings, [])
        self.assertEqual(len(cf), 1)
        self.assertEqual(cf.iloc[0][CashFlowEvent.CATEGORY], CAPEX)
        self.assertAlmostEqual(float(cf.iloc[0][CashFlowEvent.AMOUNT]), -400.0)
        self.assertFalse(
            (cf[CashFlowEvent.DESCRIPTION] == "INTEREST_PAYMENT").any()
        )

    def test_unknown_type_warns_outside_nav(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "eksport-transakcji_2026-07-22_2026-07-22.csv").write_text(
                _csv(
                    [
                        _row(tx_date="2026-07-22", tx_id="a", amount="100"),
                        _row(
                            tx_date="2026-07-22",
                            tx_id="b",
                            tx_type="WEIRD_TYPE",
                            amount="50",
                        ),
                    ]
                ),
                encoding="utf-8",
            )
            blotter = _read_traderepublic_transactions(root)
        nav, warnings = nav_as_of(blotter, date(2026, 8, 1))
        self.assertAlmostEqual(nav, 100.0, places=2)
        self.assertTrue(any("WEIRD_TYPE" in w for w in warnings))

    def test_roi_terminal_and_xirr(self):
        blotter = self._blotter()
        nav, _ = nav_as_of(blotter, date(2026, 10, 18))
        self.assertAlmostEqual(nav, 402.94, places=2)
        summary, events, _warnings = compute_traderepublic_roi(
            date(2026, 10, 18),
            blotter=blotter,
        )
        self.assertEqual(len(summary), 1)
        # roi_summary_to_row zaokrągla terminal (jak inne venue).
        self.assertEqual(int(summary.iloc[0]["terminal_unrealized"]), round(nav))
        self.assertFalse(bool(summary.iloc[0]["is_sold"]))
        cf = events[DEFAULT_TRADEREPUBLIC_ASSET_ID]
        dates, amounts = cashflows_for_xirr(cf, date(2026, 10, 18), nav)
        self.assertAlmostEqual(amounts[-1], nav, places=2)
        xirr = compute_xirr(dates, amounts)
        self.assertIsNotNone(xirr)
        self.assertGreater(float(xirr), 0.0)


if __name__ == "__main__":
    unittest.main()
