# -*- coding: utf-8 -*-
from __future__ import annotations

import zipfile
import tempfile
import unittest
from datetime import date
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from evaluators.evaluate_broker_xtb import evaluate_broker_xtb, is_xtb_broker
from importers.assets.data_model import AssetsDef, GroupDomain, KindDomain, TypeDomain
from importers.broker.data_model import (
    BrokerCashBalanceFrame,
    BrokerCashFlowFrame,
    BrokerPositionFrame,
    BrokerTransactionFrame,
)
from importers.xtb.data_model import (
    DEFAULT_XTB_ASSET_ID,
    DEFAULT_XTB_CLIENT_ID,
    XtbCashOperationsFile,
    XtbClosedPositionsFile,
    XtbOpenPositionsFile,
)
from importers.xtb.normalize import (
    normalize_xtb_cash_balances,
    normalize_xtb_cashflows,
    normalize_xtb_positions,
    normalize_xtb_transactions,
)
from importers.xtb.read_xtb import (
    _normalize_cash,
    _read_xtb_cash,
    _read_xtb_open,
    inspect_xtb_export,
    period_gap_warnings,
    xtb_open_position_rows,
    xtb_open_positions_value,
)
from maintenance.move_downloaded_results import ACTION_MOVED, ACTION_SKIPPED, KIND_XTB
from maintenance.move_xtb_files import move_xtb_files, xtb_target_name
from roi.categories import CAPEX, DIVESTMENT, REVENUES
from roi.data_model import CashFlowEvent
from roi.xtb_roi import compute_xtb_ticker_roi


class XtbInspectTests(unittest.TestCase):
    def test_inspects_xlsx_sheets_without_schema_assumptions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "xtb_export.xlsx"
            with pd.ExcelWriter(path) as writer:
                pd.DataFrame(
                    [{"Symbol": "SXR8.DE", "Quantity": 2.0, "Currency": "EUR"}]
                ).to_excel(writer, sheet_name="Open positions", index=False)
                pd.DataFrame(
                    [{"Type": "Dividend", "Amount": 10.0, "Currency": "EUR"}]
                ).to_excel(writer, sheet_name="Cash operations", index=False)

            info = inspect_xtb_export(path)

        self.assertEqual(DEFAULT_XTB_ASSET_ID, "p_xtb")
        self.assertEqual([sheet.sheet_name for sheet in info], ["Open positions", "Cash operations"])
        self.assertEqual(info[0].columns, ("Symbol", "Quantity", "Currency"))
        self.assertEqual(info[1].rows, 1)

    def test_inspects_zip_xlsx_and_detects_xtb_header_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xlsx = root / "PLN_55260027_2026-07-31_2026-08-20.xlsx"
            _write_xtb_workbook(xlsx)
            zip_path = root / "55260027_2026-07-31_2026-08-20.zip"
            _zip_file(zip_path, xlsx, "55260027/PLN_55260027_2026-07-31_2026-08-20.xlsx")

            info = inspect_xtb_export(zip_path)

        by_sheet = {sheet.sheet_name: sheet for sheet in info}
        self.assertEqual(set(by_sheet), {"Closed Positions", "Cash Operations", "Open Positions"})
        self.assertEqual(by_sheet["Closed Positions"].header_row, 4)
        self.assertEqual(by_sheet["Cash Operations"].header_row, 4)
        self.assertEqual(by_sheet["Open Positions"].header_row, 8)
        self.assertIn("Instrument/Position", by_sheet["Open Positions"].columns)
        self.assertIn("Amount", by_sheet["Cash Operations"].columns)


class MoveXtbTests(unittest.TestCase):
    def test_moves_first_zip_and_deletes_identical_iterator_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            download = root / "Downloads"
            assets = root / "assets"
            download.mkdir()
            assets.mkdir()
            source = download / "55260027_2026-07-31_2026-08-20.zip"
            duplicate = download / "55260027_2026-07-31_2026-08-20 (1).zip"
            _write_xtb_zip(source)
            _write_xtb_zip(duplicate)

            results = move_xtb_files(assets, download)

            target = assets / DEFAULT_XTB_ASSET_ID / xtb_target_name(
                DEFAULT_XTB_CLIENT_ID,
                date(2026, 7, 31),
                date(2026, 8, 20),
                data_kind="open_closed_cash",
            )
            self.assertEqual([r.action for r in results], [ACTION_MOVED, ACTION_SKIPPED])
            self.assertTrue(target.is_file())
            self.assertEqual(target.suffix, ".xlsx")
            self.assertFalse(source.exists())
            self.assertFalse(duplicate.exists())
            self.assertTrue(all(r.kind == KIND_XTB for r in results))

    def test_existing_identical_target_skips_incoming(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            download = root / "Downloads"
            assets = root / "assets"
            target_dir = assets / DEFAULT_XTB_ASSET_ID
            download.mkdir()
            target_dir.mkdir(parents=True)
            incoming = download / "55260027_2026-07-31_2026-08-20 (1).zip"
            target = target_dir / "xtb_open_closed_cash_55260027_2026-07-31_2026-08-20.xlsx"
            target.write_bytes(_xtb_workbook_bytes())
            _write_xtb_zip(incoming)

            results = move_xtb_files(assets, download)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].action, ACTION_SKIPPED)
            self.assertTrue(target.is_file())
            self.assertFalse(incoming.exists())

    def test_same_period_different_content_is_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            download = root / "Downloads"
            assets = root / "assets"
            download.mkdir()
            assets.mkdir()
            _write_xtb_zip(download / "55260027_2026-07-31_2026-08-20.zip")
            _write_xtb_zip(download / "55260027_2026-07-31_2026-08-20 (1).zip", amount=5701.0)

            with self.assertRaises(ValueError):
                move_xtb_files(assets, download)


class ReadXtbTests(unittest.TestCase):
    def test_reads_open_positions_and_free_funds_cash(self):
        with tempfile.TemporaryDirectory() as tmp:
            asset_dir = Path(tmp)
            (asset_dir / "xtb_open_closed_cash_55260027_2026-07-31_2026-08-20.xlsx").write_bytes(
                _xtb_workbook_bytes()
            )
            open_df = _read_xtb_open(asset_dir)

        XtbOpenPositionsFile.check_structure(open_df)
        self.assertEqual(len(open_df), 2)
        positions = open_df[open_df[XtbOpenPositionsFile.TICKER].astype(str).str.strip().ne("")]
        cash = open_df[open_df[XtbOpenPositionsFile.TICKER].astype(str).str.strip().eq("")]
        self.assertEqual(len(positions), 1)
        self.assertEqual(len(cash), 1)
        self.assertAlmostEqual(float(positions.iloc[0][XtbOpenPositionsFile.VALUE]), 21429.44)
        self.assertEqual(str(positions.iloc[0][XtbOpenPositionsFile.TYPE]), "BUY")
        self.assertAlmostEqual(float(cash.iloc[0][XtbOpenPositionsFile.VALUE]), 263.88)

    def test_open_drops_instrument_aggregate_when_buy_lot_exists(self):
        df = pd.DataFrame(
            [
                _open_row(
                    ticker="ETFPZUW20M40.PL",
                    value=21429.44,
                    instrument="WIG20TR + mWIG40TR",
                ),
                _open_row(
                    ticker="ETFPZUW20M40.PL",
                    value=21429.44,
                    instrument="2761661939",
                    type_="BUY",
                ),
            ]
        )
        rows = xtb_open_position_rows(df)
        self.assertEqual(len(rows), 1)
        self.assertEqual(str(rows.iloc[0][XtbOpenPositionsFile.TYPE]), "BUY")
        self.assertAlmostEqual(xtb_open_positions_value(rows), 21429.44)

    def test_open_keeps_instrument_row_when_no_lot(self):
        df = pd.DataFrame(
            [_open_row(ticker="ETFPZUW20M40.PL", value=21429.44, instrument="WIG20TR + mWIG40TR")]
        )
        rows = xtb_open_position_rows(df)
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(float(rows.iloc[0][XtbOpenPositionsFile.VALUE]), 21429.44)

    def test_merges_cash_operations_from_multiple_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            asset_dir = Path(tmp)
            (asset_dir / "xtb_open_closed_cash_55260027_2026-01-01_2026-03-31.xlsx").write_bytes(
                _xtb_workbook_bytes(
                    period_start="2026-01-01",
                    period_end="2026-03-31",
                    extra_cash=[{"Type": "Stock purchase", "Ticker": "AAA.PL", "Time": "2026-02-01", "Amount": -100.0}],
                )
            )
            (asset_dir / "xtb_open_closed_cash_55260027_2026-07-31_2026-08-20.xlsx").write_bytes(
                _xtb_workbook_bytes()
            )
            cash_df = _read_xtb_cash(asset_dir)

        tickers = set(cash_df[XtbCashOperationsFile.TICKER].astype(str).str.strip())
        self.assertIn("AAA.PL", tickers)
        self.assertIn("ETFPZUW20M40.PL", tickers)

    def test_cash_id_mixed_float_and_empty_writes_parquet(self):
        raw = pd.DataFrame(
            [
                {
                    XtbCashOperationsFile.ID: 12345.0,
                    XtbCashOperationsFile.TYPE: "Deposit",
                    XtbCashOperationsFile.INSTRUMENT: "",
                    XtbCashOperationsFile.TICKER: "",
                    XtbCashOperationsFile.ISIN: "",
                    XtbCashOperationsFile.TIME: "2026-08-17",
                    XtbCashOperationsFile.AMOUNT: 100.0,
                    XtbCashOperationsFile.COMMENT: "",
                    XtbCashOperationsFile.POSITION_ID: float("nan"),
                    XtbCashOperationsFile.BALANCE: 100.0,
                    XtbCashOperationsFile.CURRENCY: "PLN",
                },
                {
                    XtbCashOperationsFile.ID: float("nan"),
                    XtbCashOperationsFile.TYPE: "Stock purchase",
                    XtbCashOperationsFile.INSTRUMENT: "ETF",
                    XtbCashOperationsFile.TICKER: "AAA.PL",
                    XtbCashOperationsFile.ISIN: "",
                    XtbCashOperationsFile.TIME: "2026-08-18",
                    XtbCashOperationsFile.AMOUNT: -40.0,
                    XtbCashOperationsFile.COMMENT: "",
                    XtbCashOperationsFile.POSITION_ID: 99.0,
                    XtbCashOperationsFile.BALANCE: 60.0,
                    XtbCashOperationsFile.CURRENCY: "PLN",
                },
            ]
        )
        cash = _normalize_cash(raw)
        self.assertEqual(cash[XtbCashOperationsFile.ID].tolist(), ["12345", ""])
        self.assertEqual(cash[XtbCashOperationsFile.POSITION_ID].tolist(), ["", "99"])
        with tempfile.TemporaryDirectory() as tmp:
            cash.to_parquet(Path(tmp) / "p_xtb-cash.parquet")

    def test_drops_cash_total_footer_row(self):
        raw = pd.DataFrame(
            [
                {
                    XtbCashOperationsFile.ID: "1",
                    XtbCashOperationsFile.TYPE: "Deposit",
                    XtbCashOperationsFile.INSTRUMENT: "",
                    XtbCashOperationsFile.TICKER: "",
                    XtbCashOperationsFile.ISIN: "",
                    XtbCashOperationsFile.TIME: "2026-08-17",
                    XtbCashOperationsFile.AMOUNT: 100.0,
                    XtbCashOperationsFile.COMMENT: "",
                    XtbCashOperationsFile.POSITION_ID: "",
                    XtbCashOperationsFile.BALANCE: 100.0,
                    XtbCashOperationsFile.CURRENCY: "PLN",
                },
                {
                    XtbCashOperationsFile.ID: "",
                    XtbCashOperationsFile.TYPE: "Total",
                    XtbCashOperationsFile.INSTRUMENT: "",
                    XtbCashOperationsFile.TICKER: "",
                    XtbCashOperationsFile.ISIN: "",
                    XtbCashOperationsFile.TIME: "",
                    XtbCashOperationsFile.AMOUNT: 100.0,
                    XtbCashOperationsFile.COMMENT: "",
                    XtbCashOperationsFile.POSITION_ID: "",
                    XtbCashOperationsFile.BALANCE: None,
                    XtbCashOperationsFile.CURRENCY: "PLN",
                },
            ]
        )
        cash = _normalize_cash(raw)
        self.assertEqual(len(cash), 1)
        self.assertEqual(cash.iloc[0][XtbCashOperationsFile.TYPE], "Deposit")

    def test_period_gap_warning(self):
        warnings = period_gap_warnings(
            [(date(2026, 1, 1), date(2026, 3, 31)), (date(2026, 5, 1), date(2026, 8, 20))],
            "cash",
        )
        self.assertEqual(len(warnings), 1)
        self.assertIn("2026-04-01", warnings[0])


class EvaluateXtbTests(unittest.TestCase):
    def test_is_xtb_broker(self):
        self.assertTrue(is_xtb_broker(pd.Series({AssetsDef.ID: DEFAULT_XTB_ASSET_ID})))
        self.assertFalse(is_xtb_broker(pd.Series({AssetsDef.ID: "p_degiro"})))

    def test_evaluate_uses_latest_open_value_plus_cash(self):
        open_df = pd.DataFrame(
            [
                _open_row(ticker="ETFPZUW20M40.PL", volume=167, value=21429.44, instrument="WIG20TR + mWIG40TR"),
                _open_row(
                    ticker="ETFPZUW20M40.PL",
                    volume=167,
                    value=21429.44,
                    instrument="2761661939",
                    type_="BUY",
                ),
                _open_row(product="Cash", instrument="Free funds", ticker="", value=263.88, volume=None, type_="CASH"),
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asset_dir = root / DEFAULT_XTB_ASSET_ID
            asset_dir.mkdir()
            with (
                patch("evaluators.evaluate_broker_xtb.resolve_asset_dir", return_value=asset_dir),
                patch("evaluators.evaluate_broker_xtb.read_xtb_open", return_value=open_df),
            ):
                result, warnings = evaluate_broker_xtb(
                    root, DEFAULT_XTB_ASSET_ID, _catalog_row(), date(2026, 8, 20)
                )
        self.assertEqual(warnings, [])
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(float(result.iloc[0][AssetsDef.VALUE]), 21693.32)
        self.assertIn("1 poz. + 1 cash", result.iloc[0][AssetsDef.DESCR])
        self.assertEqual(result.iloc[0][AssetsDef.CURRENCY], "PLN")

    def test_evaluate_missing_dir_returns_empty(self):
        missing = Path("/tmp/definitely-missing-p_xtb")
        with patch("evaluators.evaluate_broker_xtb.resolve_asset_dir", return_value=missing):
            result, warnings = evaluate_broker_xtb(
                Path("/tmp"), DEFAULT_XTB_ASSET_ID, _catalog_row(), date(2026, 8, 20)
            )
        self.assertTrue(result.empty)
        self.assertTrue(any("Brak katalogu" in msg for msg in warnings))


class XtbRoiTests(unittest.TestCase):
    def test_compute_roi_from_cash_operations_and_open_positions_terminal(self):
        open_df = pd.DataFrame(
            [
                _open_row(
                    ticker="ETFPZUW20M40.PL",
                    volume=167,
                    value=21429.44,
                    instrument="WIG20TR + mWIG40TR",
                ),
                _open_row(
                    ticker="ETFPZUW20M40.PL",
                    volume=167,
                    value=21429.44,
                    instrument="2761661939",
                    type_="BUY",
                ),
                _open_row(product="Cash", instrument="Free funds", ticker="", value=263.88, type_="CASH"),
            ]
        )
        cash_df = pd.DataFrame(
            [
                _cash_row("Stock purchase", "ETFPZUW20M40.PL", "2026-08-18", -21436.12),
                _cash_row("Deposit", "", "2026-08-17", 5700.0),
                _cash_row("Commission", "ETFPZUW20M40.PL", "2026-08-18", -1.5),
            ]
        )
        summary, events, warnings = compute_xtb_ticker_roi(
            date(2026, 8, 20),
            cash_operations_df=cash_df,
            open_positions_df=open_df,
            closed_positions_df=pd.DataFrame(columns=list(XtbClosedPositionsFile.expected_columns())),
        )
        self.assertEqual(warnings, [])
        self.assertEqual(len(summary), 1)
        row = summary.iloc[0]
        self.assertEqual(row["asset_id"], "p_xtb:ETFPZUW20M40.PL")
        self.assertAlmostEqual(float(row["capex"]), -21436.0)
        self.assertAlmostEqual(float(row["terminal_unrealized"]), 21429.0)
        self.assertAlmostEqual(float(row["roi_nominal"]), -7.0)
        self.assertEqual(events["p_xtb:ETFPZUW20M40.PL"][CashFlowEvent.CATEGORY].tolist(), [CAPEX])
        self.assertAlmostEqual(float(row["opex"]), 0.0)

    def test_sale_dividend_unknown_type_and_closed_sold(self):
        open_df = pd.DataFrame(
            [_open_row(ticker="KEEP.PL", volume=2, value=40.0, period_end="2026-08-20")]
        )
        cash_df = pd.DataFrame(
            [
                _cash_row("Stock purchase", "KEEP.PL", "2026-01-10", -30.0),
                _cash_row("Stock purchase", "GONE.PL", "2026-01-11", -20.0),
                _cash_row("Stock sale", "GONE.PL", "2026-02-01", 22.0),
                _cash_row("Dividend", "KEEP.PL", "2026-03-01", 1.5),
                _cash_row("Loyalty bonus", "KEEP.PL", "2026-03-02", 0.4),
                _cash_row("Total", "", "", 52.4),
            ]
        )
        closed_df = pd.DataFrame(
            [_closed_row(ticker="GONE.PL", volume=1, close_time="2026-02-01")]
        )
        summary, events, warnings = compute_xtb_ticker_roi(
            date(2026, 8, 20),
            cash_operations_df=cash_df,
            open_positions_df=open_df,
            closed_positions_df=closed_df,
        )
        self.assertTrue(any("Loyalty bonus" in msg for msg in warnings))
        self.assertFalse(any("Total" in msg for msg in warnings))
        by_id = {row["asset_id"]: row for _, row in summary.iterrows()}
        self.assertIn("p_xtb:KEEP.PL", by_id)
        self.assertIn("p_xtb:GONE.PL", by_id)
        self.assertFalse(bool(by_id["p_xtb:KEEP.PL"]["is_sold"]))
        self.assertTrue(bool(by_id["p_xtb:GONE.PL"]["is_sold"]))
        self.assertEqual(
            events["p_xtb:KEEP.PL"][CashFlowEvent.CATEGORY].tolist(),
            [CAPEX, REVENUES],
        )
        self.assertEqual(
            events["p_xtb:GONE.PL"][CashFlowEvent.CATEGORY].tolist(),
            [CAPEX, DIVESTMENT],
        )


class XtbNormalizeTests(unittest.TestCase):
    def test_normalizes_xtb_frames_to_broker_model(self):
        open_df = pd.DataFrame(
            [
                _open_row(ticker="ETFPZUW20M40.PL", volume=167, value=21429.44, instrument="WIG20TR"),
                _open_row(product="Cash", instrument="Free funds", ticker="", value=263.88, type_="CASH"),
            ]
        )
        cash_df = pd.DataFrame(
            [
                _cash_row("Stock purchase", "ETFPZUW20M40.PL", "2026-08-18", -21436.12),
                _cash_row("Dividend", "ETFPZUW20M40.PL", "2026-08-19", 2.0),
                _cash_row("Deposit", "", "2026-08-17", 5700.0),
            ]
        )
        closed_df = pd.DataFrame([_closed_row(ticker="GONE.PL", volume=1, close_time="2026-02-01")])

        positions = normalize_xtb_positions(open_df)
        tx = normalize_xtb_transactions(closed_df, cash_df)
        flows = normalize_xtb_cashflows(cash_df)
        cash = normalize_xtb_cash_balances(open_df)

        BrokerPositionFrame.check_structure(positions)
        BrokerTransactionFrame.check_structure(tx)
        BrokerCashFlowFrame.check_structure(flows)
        BrokerCashBalanceFrame.check_structure(cash)
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions.iloc[0]["ticker"], "ETFPZUW20M40.PL")
        self.assertIn("BUY", set(tx["type"]))
        self.assertIn("SELL", set(tx["type"]))
        self.assertEqual(set(flows["type"]), {"DIVIDEND", "DEPOSIT"})
        self.assertAlmostEqual(float(cash.iloc[0]["amount"]), 263.88)


def _catalog_row() -> pd.Series:
    return pd.Series(
        {
            AssetsDef.ID: DEFAULT_XTB_ASSET_ID,
            AssetsDef.TYPE: TypeDomain.EQUITIES,
            AssetsDef.GROUP: GroupDomain.INVESTMENT,
            AssetsDef.DESCR: "XTB",
            AssetsDef.KIND: KindDomain.BROKER,
            AssetsDef.CURRENCY: "PLN",
            AssetsDef.NOTES: "",
        }
    )


def _open_row(
    *,
    ticker: str,
    value: float,
    volume=167,
    instrument: str = "ETF",
    product: str = "My Trades",
    type_: str = "",
    period_end: str = "2026-08-20",
) -> dict:
    return {
        XtbOpenPositionsFile.PRODUCT: product,
        XtbOpenPositionsFile.INSTRUMENT: instrument,
        XtbOpenPositionsFile.TICKER: ticker,
        XtbOpenPositionsFile.ISIN: "",
        XtbOpenPositionsFile.VOLUME: volume,
        XtbOpenPositionsFile.VALUE: value,
        XtbOpenPositionsFile.CURRENCY: "PLN",
        XtbOpenPositionsFile.TYPE: type_,
        XtbOpenPositionsFile.POSITION_ID: "",
        XtbOpenPositionsFile.FILE_DATE: period_end,
        XtbOpenPositionsFile.PERIOD_START: "2026-07-31",
        XtbOpenPositionsFile.PERIOD_END: period_end,
    }


def _cash_row(op_type: str, ticker: str, time: str, amount: float) -> dict:
    return {
        XtbCashOperationsFile.ID: "",
        XtbCashOperationsFile.TYPE: op_type,
        XtbCashOperationsFile.INSTRUMENT: ticker or "",
        XtbCashOperationsFile.TICKER: ticker,
        XtbCashOperationsFile.ISIN: "",
        XtbCashOperationsFile.TIME: time,
        XtbCashOperationsFile.AMOUNT: amount,
        XtbCashOperationsFile.COMMENT: "",
        XtbCashOperationsFile.POSITION_ID: "",
        XtbCashOperationsFile.BALANCE: None,
        XtbCashOperationsFile.CURRENCY: "PLN",
        XtbCashOperationsFile.FILE_DATE: "2026-08-20",
        XtbCashOperationsFile.PERIOD_START: "2026-07-31",
        XtbCashOperationsFile.PERIOD_END: "2026-08-20",
    }


def _closed_row(*, ticker: str, volume: float, close_time: str) -> dict:
    return {
        XtbClosedPositionsFile.INSTRUMENT: ticker,
        XtbClosedPositionsFile.TICKER: ticker,
        XtbClosedPositionsFile.ISIN: "",
        XtbClosedPositionsFile.VOLUME: volume,
        XtbClosedPositionsFile.OPEN_PRICE: 20.0,
        XtbClosedPositionsFile.CLOSE_PRICE: 22.0,
        XtbClosedPositionsFile.OPEN_TIME: "2026-01-11",
        XtbClosedPositionsFile.CLOSE_TIME: close_time,
        XtbClosedPositionsFile.POSITION_ID: "pos-1",
        XtbClosedPositionsFile.PROFIT: 2.0,
        XtbClosedPositionsFile.FILE_DATE: "2026-08-20",
        XtbClosedPositionsFile.PERIOD_START: "2026-07-31",
        XtbClosedPositionsFile.PERIOD_END: "2026-08-20",
    }


def _write_xtb_zip(path: Path, *, amount: float = 5700.0) -> None:
    payload = _xtb_workbook_bytes(amount=amount)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("55260027/PLN_55260027_2026-07-31_2026-08-20.xlsx", payload)


def _zip_file(zip_path: Path, source: Path, arcname: str) -> None:
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.write(source, arcname)


def _write_xtb_workbook(path: Path) -> None:
    path.write_bytes(_xtb_workbook_bytes())


def _xtb_workbook_bytes(
    *,
    amount: float = 5700.0,
    period_start: str = "2026-07-31",
    period_end: str = "2026-08-20",
    extra_cash: list[dict] | None = None,
    open_rows: list[list] | None = None,
    cash_amount: float | None = 263.88,
) -> bytes:
    closed = pd.DataFrame(
        [
            ["Account number", "55260027", None, None, None],
            ["Closed Positions", None, None, None, None],
            ["Date from (UTC)", period_start, None, None, None],
            ["Date to (UTC)", period_end, None, None, None],
            ["Instrument", "Ticker", "Volume", "Open Price", "Position ID"],
            ["Profit/loss", None, None, None, None],
        ]
    )
    cash_rows = [
        ["Account number", "55260027", None, None, None],
        ["Cash Operations", None, None, None, None],
        ["Date from (UTC)", period_start, None, None, None],
        ["Date to (UTC)", period_end, None, None, None],
        ["Type", "Instrument", "Ticker", "Time", "Amount"],
        ["Stock purchase", "WIG20TR + mWIG40TR", "ETFPZUW20M40.PL", "2026-08-18", -21436.12],
        ["Deposit", None, None, "2026-08-17", amount],
    ]
    if extra_cash:
        for item in extra_cash:
            cash_rows.append(
                [
                    item.get("Type"),
                    item.get("Instrument") or item.get("Ticker"),
                    item.get("Ticker"),
                    item.get("Time"),
                    item.get("Amount"),
                ]
            )
    cash = pd.DataFrame(cash_rows)
    if open_rows is None:
        summary_cash = (
            ["Cash", "Free funds", cash_amount, "PLN", None] if cash_amount is not None else [None, None, None, None, None]
        )
        open_positions = pd.DataFrame(
            [
                ["Account number", "55260027", None, None, None],
                ["Open Positions", None, None, None, None],
                ["Data as of report generated", period_end, None, None, None],
                ["Product", "Metric", "Amount", "Currency", None],
                ["My Trades", "Value", 21429.44, "PLN", None],
                ["My Trades", "Profit", -6.68, "PLN", None],
                summary_cash,
                ["Note", "Summary values and open positions are shown as of the report generation time", None, None, None],
                ["Product", "Instrument/Position", "Ticker", "Category", "Type", "Volume", "Value"],
                ["My Trades", "WIG20TR + mWIG40TR", "ETFPZUW20M40.PL", "ETF", None, 167, 21429.44],
                ["My Trades", "2761661939", "ETFPZUW20M40.PL", None, "BUY", 167, 21429.44],
            ]
        )
    else:
        open_positions = pd.DataFrame(open_rows)

    output = BytesIO()
    with pd.ExcelWriter(output) as writer:
        closed.to_excel(writer, sheet_name="Closed Positions", header=False, index=False)
        cash.to_excel(writer, sheet_name="Cash Operations", header=False, index=False)
        open_positions.to_excel(writer, sheet_name="Open Positions", header=False, index=False)
    return output.getvalue()


if __name__ == "__main__":
    unittest.main()
