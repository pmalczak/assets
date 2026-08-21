import unittest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd

from app_proc.calculate_assets import ASSETS_SNAPSHOT_STEP
from app_proc.recalculate_snapshots import (
    PORTFOLIO_WINDOW_DAYS,
    SNAPSHOT_JOB_RESULT_PREFIX,
    SnapshotResult,
    encode_snapshot_job_results,
    parse_snapshot_job_stdout,
    recalculate_today_snapshot,
    recalculate_weekly_snapshots,
    run_snapshot_job_isolated,
    snapshot_results_to_dataframe,
    valuation_dates_in_window,
)
from importers.assets.data_model import AssetsDef


class ValuationDatesTests(unittest.TestCase):
    def test_valuation_dates_includes_weekday_snapshots_only(self):
        reference = date(2026, 7, 15)  # Wednesday
        dates = valuation_dates_in_window(reference)
        self.assertIn(reference, dates)
        self.assertTrue(all(d.weekday() in (1, 2, 4, 6) for d in dates))
        self.assertGreaterEqual(min(dates), reference - timedelta(days=PORTFOLIO_WINDOW_DAYS))


class RecalculateTodaySnapshotTests(unittest.TestCase):
    @patch("app_proc.recalculate_snapshots.calculate_assets")
    def test_recalculate_today_snapshot_returns_snapshot_result(self, calculate_assets_mock):
        assets = pd.DataFrame([{AssetsDef.VALUE_PLN: 100}, {AssetsDef.VALUE_PLN: 50}])
        calculate_assets_mock.return_value = assets

        result = recalculate_today_snapshot(force_read_all_data=True)

        calculate_assets_mock.assert_called_once_with(
            valuation_date=date.today(),
            force_read_all_data=True,
        )
        self.assertEqual(result.valuation_date, date.today())
        self.assertEqual(result.rows, 2)
        self.assertEqual(result.total_pln, 150)
        self.assertEqual(result.resource, f"{ASSETS_SNAPSHOT_STEP}/{date.today():%Y-%m-%d}.parquet")


    @patch("app_proc.recalculate_snapshots.calculate_assets")
    @patch("app_proc.recalculate_snapshots.DATA_STEP")
    def test_without_force_invalidates_today_snapshot(
        self, data_step_mock, calculate_assets_mock
    ):
        calculate_assets_mock.return_value = pd.DataFrame([{AssetsDef.VALUE_PLN: 1}])

        recalculate_today_snapshot(force_read_all_data=False)

        data_step_mock.invalidate.assert_called_once_with(
            f"{ASSETS_SNAPSHOT_STEP}/{date.today():%Y-%m-%d}.parquet"
        )
        calculate_assets_mock.assert_called_once_with(
            valuation_date=date.today(),
            force_read_all_data=False,
        )


class SnapshotJobProtocolTests(unittest.TestCase):
    def test_encode_parse_roundtrip(self):
        results = [
            SnapshotResult(
                valuation_date=date(2026, 8, 21),
                rows=46,
                total_pln=12001473,
                resource=f"{ASSETS_SNAPSHOT_STEP}/2026-08-21.parquet",
            )
        ]
        stdout = "log line\n" + encode_snapshot_job_results(results) + "\n"
        parsed = parse_snapshot_job_stdout(stdout)
        self.assertEqual(parsed, results)
        self.assertTrue(encode_snapshot_job_results(results).startswith(SNAPSHOT_JOB_RESULT_PREFIX))

    def test_parse_raises_without_marker(self):
        with self.assertRaises(RuntimeError):
            parse_snapshot_job_stdout("only logs, no marker")


class RunSnapshotJobIsolatedTests(unittest.TestCase):
    @patch("app_proc.recalculate_snapshots.subprocess.run")
    def test_isolated_job_parses_child_stdout(self, run_mock):
        result = SnapshotResult(
            valuation_date=date(2026, 8, 21),
            rows=2,
            total_pln=10,
            resource=f"{ASSETS_SNAPSHOT_STEP}/2026-08-21.parquet",
        )
        run_mock.return_value = MagicMock(
            returncode=0,
            stdout=encode_snapshot_job_results([result]) + "\n",
            stderr="",
        )

        parsed = run_snapshot_job_isolated(weekly=False, force_read_all_data=False)

        self.assertEqual(parsed, [result])
        cmd = run_mock.call_args.args[0]
        self.assertIn("--today", cmd)
        self.assertNotIn("--force", cmd)

    @patch("app_proc.recalculate_snapshots.subprocess.run")
    def test_isolated_job_raises_on_segfault(self, run_mock):
        run_mock.return_value = MagicMock(returncode=-11, stdout="partial", stderr="Fatal Python")
        with self.assertRaises(RuntimeError) as ctx:
            run_snapshot_job_isolated(weekly=False, force_read_all_data=True)
        self.assertIn("segfault", str(ctx.exception))
        cmd = run_mock.call_args.args[0]
        self.assertIn("--force", cmd)


class RecalculateWeeklySnapshotsTests(unittest.TestCase):
    @patch("app_proc.recalculate_snapshots.calculate_assets")
    def test_recalculate_weekly_snapshots_returns_results_for_each_date(self, calculate_assets_mock):
        reference = date(2026, 7, 15)
        dates = valuation_dates_in_window(reference)
        calculate_assets_mock.return_value = pd.DataFrame([{AssetsDef.VALUE_PLN: 10}])

        results = recalculate_weekly_snapshots(
            reference=reference,
            force_read_all_data=True,
        )

        self.assertEqual(len(results), len(dates))
        self.assertEqual(calculate_assets_mock.call_count, len(dates))
        first_call = calculate_assets_mock.call_args_list[0]
        self.assertTrue(first_call.kwargs["force_read_all_data"])
        second_call = calculate_assets_mock.call_args_list[1]
        self.assertFalse(second_call.kwargs["force_read_all_data"])
        self.assertIsInstance(results[0], SnapshotResult)


class SnapshotResultsToDataframeTests(unittest.TestCase):
    def test_snapshot_results_to_dataframe_maps_columns(self):
        results = [
            SnapshotResult(
                valuation_date=date(2026, 7, 15),
                rows=3,
                total_pln=1000,
                resource=f"{ASSETS_SNAPSHOT_STEP}/2026-07-15.parquet",
            )
        ]
        df = snapshot_results_to_dataframe(results)
        self.assertEqual(list(df.columns), ["Data wyceny", "Wiersze", "Suma PLN", "Plik snapshotu"])
        self.assertEqual(df.iloc[0]["Wiersze"], 3)


if __name__ == "__main__":
    unittest.main()
