# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from maintenance.prune_stale_data_steps import (
    ACTION_DELETED,
    ACTION_STALE,
    find_stale_schema_dirs,
    format_stale_results,
    prune_stale_data_steps,
)


class FindStaleSchemaDirsTests(unittest.TestCase):
    def test_keeps_active_schema_lists_older(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            date_dir = root / "11 portfolio_cf" / "2026-10-02"
            (date_dir / "s3").mkdir(parents=True)
            (date_dir / "s5").mkdir(parents=True)
            (date_dir / "s3" / "_ledger.parquet").write_bytes(b"old")
            (date_dir / "s5" / "_ledger.parquet").write_bytes(b"new")
            with patch(
                "maintenance.prune_stale_data_steps.active_schema_products",
                return_value={"11 portfolio_cf": 5},
            ), patch(
                "maintenance.prune_stale_data_steps.obsolete_data_step_products",
                return_value=(),
            ):
                found = find_stale_schema_dirs(root)
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0].schema, 3)
            self.assertEqual(found[0].active_schema, 5)
            self.assertEqual(found[0].action, ACTION_STALE)
            self.assertTrue((date_dir / "s5").is_dir())

    def test_ignores_unrelated_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "09 assets").mkdir(parents=True)
            (root / "11 portfolio_cf" / "2026-10-02" / "notes").mkdir(parents=True)
            with patch(
                "maintenance.prune_stale_data_steps.active_schema_products",
                return_value={"11 portfolio_cf": 5},
            ), patch(
                "maintenance.prune_stale_data_steps.obsolete_data_step_products",
                return_value=(),
            ):
                self.assertEqual(find_stale_schema_dirs(root), [])

    def test_lists_obsolete_flat_asset_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            flat = root / "09 assets" / "2026-10-02.parquet"
            flat.parent.mkdir(parents=True)
            flat.write_bytes(b"old")
            active = root / "09 assets" / "2026-10-04" / "s1"
            active.mkdir(parents=True)
            (active / "_assets.parquet").write_bytes(b"new")
            with patch(
                "maintenance.prune_stale_data_steps.active_schema_products",
                return_value={"09 assets": 1},
            ), patch(
                "maintenance.prune_stale_data_steps.obsolete_data_step_products",
                return_value=(),
            ):
                found = find_stale_schema_dirs(root)
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0].path, flat)
            self.assertEqual(found[0].kind, "obsolete_flat")

    def test_lists_obsolete_product_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            obsolete = root / "10 roi" / "2026-10-02"
            obsolete.mkdir(parents=True)
            with patch(
                "maintenance.prune_stale_data_steps.active_schema_products",
                return_value={"11 portfolio_cf": 6},
            ), patch(
                "maintenance.prune_stale_data_steps.obsolete_data_step_products",
                return_value=("10 roi",),
            ):
                found = find_stale_schema_dirs(root)
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0].product, "10 roi")
            self.assertEqual(found[0].path, root / "10 roi")


class PruneStaleDataStepsTests(unittest.TestCase):
    def test_delete_removes_stale_dir_and_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            date_dir = root / "11 portfolio_cf" / "2026-10-02"
            stale = date_dir / "s3"
            active = date_dir / "s5"
            stale.mkdir(parents=True)
            active.mkdir(parents=True)
            ledger = stale / "_ledger.parquet"
            ledger.write_bytes(b"old")
            (active / "_ledger.parquet").write_bytes(b"new")
            meta_path = root / "_metadata.json"
            meta_path.write_text(
                json.dumps(
                    {
                        "11 portfolio_cf/2026-10-02/s3/_ledger.parquet": {
                            "dependencies": [],
                            "digest": "x",
                        },
                        "11 portfolio_cf/2026-10-02/s5/_ledger.parquet": {
                            "dependencies": [],
                            "digest": "y",
                        },
                    }
                ),
                encoding="utf-8",
            )
            with patch(
                "maintenance.prune_stale_data_steps.active_schema_products",
                return_value={"11 portfolio_cf": 5},
            ), patch(
                "maintenance.prune_stale_data_steps.obsolete_data_step_products",
                return_value=(),
            ):
                dry = prune_stale_data_steps(root, delete=False)
                self.assertEqual(len(dry), 1)
                self.assertTrue(stale.is_dir())

                deleted = prune_stale_data_steps(root, delete=True)
            self.assertEqual(len(deleted), 1)
            self.assertEqual(deleted[0].action, ACTION_DELETED)
            self.assertFalse(stale.exists())
            self.assertTrue(active.is_dir())
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            self.assertNotIn("11 portfolio_cf/2026-10-02/s3/_ledger.parquet", meta)
            self.assertIn("11 portfolio_cf/2026-10-02/s5/_ledger.parquet", meta)

    def test_format_mentions_active_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "11 portfolio_cf" / "2026-10-02" / "s3"
            path.mkdir(parents=True)
            with patch(
                "maintenance.prune_stale_data_steps.active_schema_products",
                return_value={"11 portfolio_cf": 5},
            ), patch(
                "maintenance.prune_stale_data_steps.obsolete_data_step_products",
                return_value=(),
            ):
                found = find_stale_schema_dirs(root)
            text = format_stale_results(found, root)
            self.assertIn("aktywny s5", text)
            self.assertIn("s3", text)


if __name__ == "__main__":
    unittest.main()
