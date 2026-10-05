# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from app_proc.assets_snapshot_step import (
    ASSETS_SNAPSHOT_FILE,
    ASSETS_SNAPSHOT_SCHEMA,
    assets_snapshot_resource,
)
from app_proc.snapshots import list_snapshot_files


class ListSnapshotFilesTests(unittest.TestCase):
    def test_lists_only_active_schema_assets_parquet(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            day = date(2026, 10, 4)
            active = root / "2026-10-04" / f"s{ASSETS_SNAPSHOT_SCHEMA}"
            active.mkdir(parents=True)
            (active / ASSETS_SNAPSHOT_FILE).write_bytes(b"ok")
            old = root / "2026-10-03" / "s0"
            old.mkdir(parents=True)
            (old / ASSETS_SNAPSHOT_FILE).write_bytes(b"old")
            (root / "2026-10-02.parquet").write_bytes(b"flat")
            listed = list_snapshot_files(root)
            self.assertEqual(listed, [(day, active / ASSETS_SNAPSHOT_FILE)])

    def test_resource_token_matches_listed_relative_path(self):
        token = assets_snapshot_resource(date(2026, 10, 4))
        self.assertEqual(
            token,
            f"snapshots/2026-10-04/s{ASSETS_SNAPSHOT_SCHEMA}/{ASSETS_SNAPSHOT_FILE}",
        )


if __name__ == "__main__":
    unittest.main()
