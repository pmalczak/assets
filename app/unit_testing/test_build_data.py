from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from app_streamlit.build_data import build_data
from importers.assets.data_model import AssetsDef


class BuildDataLatestSnapshotTests(unittest.TestCase):
    def test_empty_when_no_snapshots(self):
        with (
            patch("app_streamlit.build_data.snapshots_directory", return_value=Path("missing")),
            patch("app_streamlit.build_data.list_snapshot_files", return_value=[]),
        ):
            data = build_data.__wrapped__(_schema=4)
        self.assertIsNone(data["latest_snapshot_date"])
        self.assertTrue(data["latest_snapshot"].empty)
        self.assertEqual(data["snapshot_total_pln"], 0.0)

    def test_loads_last_snapshot_and_sums_pln(self):
        day = date(2026, 10, 4)
        path = Path("2026-10-04.parquet")
        assets = pd.DataFrame({AssetsDef.VALUE_PLN: [100.4, 50.2]})
        with (
            patch("app_streamlit.build_data.snapshots_directory", return_value=Path(".")),
            patch(
                "app_streamlit.build_data.list_snapshot_files",
                return_value=[(day, path)],
            ),
            patch("app_streamlit.build_data.load_snapshot", return_value=assets),
        ):
            data = build_data.__wrapped__(_schema=4)
        self.assertEqual(data["latest_snapshot_date"], day)
        self.assertAlmostEqual(data["snapshot_total_pln"], 150.6)
        self.assertNotIn("history", data)
        self.assertNotIn("timeline_events", data)


if __name__ == "__main__":
    unittest.main()
