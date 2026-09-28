# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd

from portfolio_cf.data_model import InstrumentCashFlow
from portfolio_cf.products import (
    coverage_resource,
    ledger_resource,
    load_assembly,
    load_portfolio_xirr_map,
    xirr_resource,
)
from portfolios.assignment import PORTFOLIO_CASH_POOL, PORTFOLIO_GM


class PortfolioCfProductsTests(unittest.TestCase):
    def test_resource_tokens_include_date(self):
        day = date(2026, 9, 28)
        self.assertEqual(
            ledger_resource(day),
            "11 portfolio_cf/2026-09-28/s3/_ledger.parquet",
        )
        self.assertEqual(
            coverage_resource(day),
            "11 portfolio_cf/2026-09-28/s3/_coverage.parquet",
        )
        self.assertEqual(
            xirr_resource(day),
            "11 portfolio_cf/2026-09-28/s3/_xirr.parquet",
        )

    @patch("portfolio_cf.products.DATA_STEP")
    @patch("portfolio_cf.products.snapshot_parquet_path")
    def test_load_assembly_uses_obtain_dependent_when_snapshot_exists(
        self,
        snap_path_mock,
        data_step_mock,
    ):
        day = date(2026, 9, 28)
        path = MagicMock()
        path.is_file.return_value = True
        snap_path_mock.return_value = path

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
        self.assertEqual(data_step_mock.obtain_dependent.call_count, 3)
        data_step_mock.obtain.assert_not_called()
        first_args = data_step_mock.obtain_dependent.call_args_list[0].args
        self.assertEqual(first_args[0], ledger_resource(day))
        self.assertEqual(first_args[2], path)

    @patch("portfolio_cf.products._obtain_xirr_table")
    def test_load_portfolio_xirr_map_filters_sold_mode(self, table_mock):
        table_mock.return_value = pd.DataFrame(
            [
                {
                    "portfolio": PORTFOLIO_GM,
                    "sold_filter": "Wszystkie",
                    "xirr": 0.12,
                    "xirr_pln": 0.11,
                    "roi_pln": 100.0,
                    "roi_local": 80.0,
                    "roi_fx": 20.0,
                    "fx_share": 0.2,
                },
                {
                    "portfolio": PORTFOLIO_GM,
                    "sold_filter": "Niesprzedane",
                    "xirr": 0.08,
                    "xirr_pln": 0.07,
                    "roi_pln": 50.0,
                    "roi_local": 40.0,
                    "roi_fx": 10.0,
                    "fx_share": 0.2,
                },
                {
                    "portfolio": PORTFOLIO_CASH_POOL,
                    "sold_filter": "Wszystkie",
                    "xirr": None,
                    "xirr_pln": None,
                    "roi_pln": None,
                    "roi_local": None,
                    "roi_fx": None,
                    "fx_share": None,
                },
            ]
        )
        mapping = load_portfolio_xirr_map(date(2026, 9, 28), "Niesprzedane")
        self.assertEqual(mapping[PORTFOLIO_GM], 0.08)
        self.assertNotIn(PORTFOLIO_CASH_POOL, mapping)

        from portfolio_cf.products import load_portfolio_metrics_map

        metrics = load_portfolio_metrics_map(date(2026, 9, 28), "Niesprzedane")
        self.assertAlmostEqual(metrics[PORTFOLIO_GM]["fx_share"], 0.2)
        self.assertAlmostEqual(metrics[PORTFOLIO_GM]["xirr_pln"], 0.07)


if __name__ == "__main__":
    unittest.main()
