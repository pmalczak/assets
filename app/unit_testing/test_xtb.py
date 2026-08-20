# -*- coding: utf-8 -*-
from __future__ import annotations

import zipfile
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from evaluators.evaluate_broker_xtb import evaluate_broker_xtb, is_xtb_broker
from importers.assets.data_model import AssetsDef, GroupDomain, KindDomain, TypeDomain
from importers.xtb.data_model import DEFAULT_XTB_ASSET_ID, DEFAULT_XTB_CLIENT_ID
from importers.xtb.read_xtb import inspect_xtb_export
from maintenance.move_downloaded_results import ACTION_MOVED, ACTION_SKIPPED, KIND_XTB
from maintenance.move_xtb_files import move_xtb_files, xtb_target_name
from roi.categories import CAPEX
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


class EvaluateXtbTests(unittest.TestCase):
    def test_is_xtb_broker(self):
        self.assertTrue(is_xtb_broker(pd.Series({AssetsDef.ID: DEFAULT_XTB_ASSET_ID})))
        self.assertFalse(is_xtb_broker(pd.Series({AssetsDef.ID: "p_degiro"})))

    def test_evaluate_uses_latest_open_report_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asset_dir = root / DEFAULT_XTB_ASSET_ID
            asset_dir.mkdir()
            (asset_dir / "xtb_open_closed_cash_55260027_2026-07-31_2026-08-20.xlsx").write_bytes(
                _xtb_workbook_bytes()
            )
            with patch("evaluators.evaluate_broker_xtb.resolve_asset_dir", return_value=asset_dir):
                result, warnings = evaluate_broker_xtb(
                    root, DEFAULT_XTB_ASSET_ID, _catalog_row(), date(2026, 8, 20)
                )
        self.assertEqual(warnings, [])
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(float(result.iloc[0][AssetsDef.VALUE]), 21429.44)
        self.assertIn("1 poz.", result.iloc[0][AssetsDef.DESCR])


class XtbRoiTests(unittest.TestCase):
    def test_compute_roi_from_cash_operations_and_open_positions_terminal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "xtb_open_closed_cash_55260027_2026-07-31_2026-08-20.xlsx"
            report.write_bytes(_xtb_workbook_bytes())
            from importers.xtb.read_xtb import read_xtb_cash_operations, read_xtb_open_positions

            summary, events, warnings = compute_xtb_ticker_roi(
                date(2026, 8, 20),
                cash_operations_df=read_xtb_cash_operations(report),
                open_positions_df=read_xtb_open_positions(report),
            )
        self.assertEqual(warnings, [])
        self.assertEqual(len(summary), 1)
        row = summary.iloc[0]
        self.assertEqual(row["asset_id"], "p_xtb:ETFPZUW20M40.PL")
        self.assertAlmostEqual(float(row["capex"]), -21436.0)
        self.assertAlmostEqual(float(row["terminal_unrealized"]), 21429.0)
        self.assertAlmostEqual(float(row["roi_nominal"]), -7.0)
        self.assertEqual(events["p_xtb:ETFPZUW20M40.PL"][CashFlowEvent.CATEGORY].tolist(), [CAPEX])


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


def _write_xtb_zip(path: Path, *, amount: float = 5700.0) -> None:
    payload = _xtb_workbook_bytes(amount=amount)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("55260027/PLN_55260027_2026-07-31_2026-08-20.xlsx", payload)


def _zip_file(zip_path: Path, source: Path, arcname: str) -> None:
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.write(source, arcname)


def _write_xtb_workbook(path: Path) -> None:
    path.write_bytes(_xtb_workbook_bytes())


def _xtb_workbook_bytes(*, amount: float = 5700.0) -> bytes:
    from io import BytesIO

    closed = pd.DataFrame(
        [
            ["Account number", "55260027", None, None, None],
            ["Closed Positions", None, None, None, None],
            ["Date from (UTC)", "2026-07-31", None, None, None],
            ["Date to (UTC)", "2026-08-20", None, None, None],
            ["Instrument", "Ticker", "Volume", "Open Price", "Position ID"],
            ["Profit/loss", None, None, None, None],
        ]
    )
    cash = pd.DataFrame(
        [
            ["Account number", "55260027", None, None, None],
            ["Cash Operations", None, None, None, None],
            ["Date from (UTC)", "2026-07-31", None, None, None],
            ["Date to (UTC)", "2026-08-20", None, None, None],
            ["Type", "Instrument", "Ticker", "Time", "Amount"],
            ["Stock purchase", "WIG20TR + mWIG40TR", "ETFPZUW20M40.PL", "2026-08-18", -21436.12],
            ["Deposit", None, None, "2026-08-17", amount],
        ]
    )
    open_positions = pd.DataFrame(
        [
            ["Account number", "55260027", None, None, None],
            ["Open Positions", None, None, None, None],
            ["Data as of report generated", "2026-08-20", None, None, None],
            ["Product", "Metric", "Amount", "Currency", None],
            ["My Trades", "Value", 21429.44, "PLN", None],
            ["My Trades", "Profit", -6.68, "PLN", None],
            [None, None, None, None, None],
            ["Note", "Summary values and open positions are shown as of the report generation time", None, None, None],
            ["Product", "Instrument/Position", "Ticker", "Volume", "Value"],
            ["My Trades", "WIG20TR + mWIG40TR", "ETFPZUW20M40.PL", 167, 21429.44],
        ]
    )
    output = BytesIO()
    with pd.ExcelWriter(output) as writer:
        closed.to_excel(writer, sheet_name="Closed Positions", header=False, index=False)
        cash.to_excel(writer, sheet_name="Cash Operations", header=False, index=False)
        open_positions.to_excel(writer, sheet_name="Open Positions", header=False, index=False)
    return output.getvalue()


if __name__ == "__main__":
    unittest.main()
