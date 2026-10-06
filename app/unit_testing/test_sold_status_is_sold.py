# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd

from portfolio_cf.adapters.base import empty_ledger
from portfolio_cf.assemble import build_instrument_ledger
from portfolio_cf.coverage import CoverageStatus, InstrumentCoverage
from portfolio_cf.sold_status import build_instrument_sold_map


def _empty_adapter(_vd, **_kwargs):
    return empty_ledger(), [], []


class SoldMapCatalogHardFailTests(unittest.TestCase):
    def test_catalog_loader_exception_propagates(self):
        with (
            patch(
                "portfolio_cf.sold_status._load_catalog_sold",
                side_effect=RuntimeError("roi summary failed"),
            ),
            patch("portfolio_cf.sold_status._load_robo_sold", return_value={}),
            patch("portfolio_cf.sold_status._load_degiro_sold", return_value={}),
            patch("portfolio_cf.sold_status._load_xtb_sold", return_value={}),
            patch("portfolio_cf.sold_status._load_bonds_sold", return_value={}),
            patch(
                "portfolio_cf.sold_status._load_revolut_deposits_sold", return_value={}
            ),
            patch("portfolio_cf.sold_status._load_mbank_deposits_sold", return_value={}),
        ):
            with self.assertRaisesRegex(RuntimeError, "roi summary failed"):
                build_instrument_sold_map(date(2026, 10, 6))

    def test_catalog_summary_sibling_skips_nested_load(self):
        summary = pd.DataFrame(
            [
                {"asset_id": "horbaczewskiego", "is_sold": True},
                {"asset_id": "aquamarina", "is_sold": False},
            ]
        )
        with (
            patch(
                "portfolio_cf.sold_status._load_catalog_sold",
                side_effect=AssertionError("must not nest load_roi_summary"),
            ) as load_mock,
            patch("portfolio_cf.sold_status._load_robo_sold", return_value={}),
            patch("portfolio_cf.sold_status._load_degiro_sold", return_value={}),
            patch("portfolio_cf.sold_status._load_xtb_sold", return_value={}),
            patch("portfolio_cf.sold_status._load_bonds_sold", return_value={}),
            patch(
                "portfolio_cf.sold_status._load_revolut_deposits_sold", return_value={}
            ),
            patch("portfolio_cf.sold_status._load_mbank_deposits_sold", return_value={}),
        ):
            sold = build_instrument_sold_map(
                date(2026, 10, 6), catalog_summary=summary
            )
        load_mock.assert_not_called()
        self.assertTrue(sold["horbaczewskiego"])
        self.assertFalse(sold["aquamarina"])

    def test_soft_venue_failure_does_not_block_catalog(self):
        summary = pd.DataFrame([{"asset_id": "ppe", "is_sold": False}])
        with (
            patch(
                "portfolio_cf.sold_status._load_robo_sold",
                side_effect=ValueError("robo down"),
            ),
            patch("portfolio_cf.sold_status._load_degiro_sold", return_value={}),
            patch("portfolio_cf.sold_status._load_xtb_sold", return_value={}),
            patch("portfolio_cf.sold_status._load_bonds_sold", return_value={}),
            patch(
                "portfolio_cf.sold_status._load_revolut_deposits_sold", return_value={}
            ),
            patch("portfolio_cf.sold_status._load_mbank_deposits_sold", return_value={}),
        ):
            sold = build_instrument_sold_map(
                date(2026, 10, 6), catalog_summary=summary
            )
        self.assertFalse(sold["ppe"])


class AssembleCatalogSoldTests(unittest.TestCase):
    def test_coverage_gets_is_sold_from_catalog_summary(self):
        def _catalog(_vd, **_kwargs):
            cov = [
                InstrumentCoverage(
                    instrument_id="horbaczewskiego",
                    status=CoverageStatus.COVERED,
                    reason="test",
                    venue="catalog",
                )
            ]
            return empty_ledger(), cov, []

        summary = pd.DataFrame(
            [{"asset_id": "horbaczewskiego", "is_sold": True}]
        )
        with (
            patch("portfolio_cf.assemble.adapt_catalog_ledger", side_effect=_catalog),
            patch("portfolio_cf.assemble.adapt_robo_ledger", side_effect=_empty_adapter),
            patch(
                "portfolio_cf.assemble.adapt_degiro_ledger", side_effect=_empty_adapter
            ),
            patch("portfolio_cf.assemble.adapt_xtb_ledger", side_effect=_empty_adapter),
            patch("portfolio_cf.assemble.adapt_bonds_ledger", side_effect=_empty_adapter),
            patch(
                "portfolio_cf.assemble.adapt_deposits_ledger", side_effect=_empty_adapter
            ),
            patch("portfolio_cf.assemble.adapt_ike_ledger", side_effect=_empty_adapter),
        ):
            asm = build_instrument_ledger(
                date(2026, 10, 6), catalog_summary=summary
            )

        self.assertTrue(asm.is_sold_by_instrument["horbaczewskiego"])
        frame = asm.coverage_frame()
        row = frame.loc[frame["instrument_id"] == "horbaczewskiego"].iloc[0]
        self.assertTrue(bool(row["is_sold"]))

    def test_catalog_sold_failure_aborts_assemble(self):
        with (
            patch(
                "portfolio_cf.assemble.adapt_catalog_ledger", side_effect=_empty_adapter
            ),
            patch("portfolio_cf.assemble.adapt_robo_ledger", side_effect=_empty_adapter),
            patch(
                "portfolio_cf.assemble.adapt_degiro_ledger", side_effect=_empty_adapter
            ),
            patch("portfolio_cf.assemble.adapt_xtb_ledger", side_effect=_empty_adapter),
            patch("portfolio_cf.assemble.adapt_bonds_ledger", side_effect=_empty_adapter),
            patch(
                "portfolio_cf.assemble.adapt_deposits_ledger", side_effect=_empty_adapter
            ),
            patch("portfolio_cf.assemble.adapt_ike_ledger", side_effect=_empty_adapter),
            patch(
                "portfolio_cf.sold_status.build_instrument_sold_map",
                side_effect=RuntimeError("missing _roi_summary"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "missing _roi_summary"):
                build_instrument_ledger(date(2026, 10, 6))


class ProductsRoiSummarySiblingTests(unittest.TestCase):
    @patch("portfolio_cf.products._obtain_roi_summary_sibling")
    @patch("portfolio_cf.products.DATA_STEP")
    @patch("portfolio_cf.products.snapshot_parquet_path")
    def test_load_assembly_passes_roi_summary_to_ledger(
        self,
        snap_path_mock,
        data_step_mock,
        roi_sibling_mock,
    ):
        from portfolio_cf.data_model import InstrumentCashFlow
        from portfolio_cf.products import ledger_resource, load_assembly

        day = date(2026, 10, 6)
        path = MagicMock()
        path.is_file.return_value = True
        snap_path_mock.return_value = path

        roi_frame = MagicMock()
        roi_frame.data_frame.return_value = pd.DataFrame(
            [{"asset_id": "horbaczewskiego", "is_sold": True}]
        )
        roi_sibling_mock.return_value = roi_frame

        ledger = pd.DataFrame(columns=list(InstrumentCashFlow.COLUMN_ORDER))
        coverage = pd.DataFrame(
            columns=["instrument_id", "status", "reason", "venue", "is_sold"]
        )
        warnings = pd.DataFrame(columns=["message"])

        def _frame(df):
            frame = MagicMock()
            frame.data_frame.return_value = df
            return frame

        data_step_mock.obtain_dependent.side_effect = [
            _frame(ledger),
            _frame(coverage),
            _frame(warnings),
        ]

        assembly = load_assembly(day)
        self.assertTrue(assembly.ledger.empty)
        roi_sibling_mock.assert_called_once_with(day)
        self.assertEqual(data_step_mock.obtain_dependent.call_count, 3)
        first_kwargs = data_step_mock.obtain_dependent.call_args_list[0].kwargs
        self.assertIs(first_kwargs["roi_summary"], roi_frame)
        self.assertEqual(
            data_step_mock.obtain_dependent.call_args_list[0].args[0],
            ledger_resource(day),
        )


if __name__ == "__main__":
    unittest.main()
