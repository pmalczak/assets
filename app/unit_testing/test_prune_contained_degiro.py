# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from maintenance.prune_contained_degiro import (
    audit_degiro_statements,
    find_degiro_gaps,
    parse_degiro_export,
    prune_contained_degiro,
)
from maintenance.prune_contained_statements import ACTION_CONTAINED, ACTION_DELETED, ACTION_SKIPPED


def _touch(root: Path, name: str) -> Path:
    path = root / "p_degiro" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")
    return path


class ParseDegiroExportTests(unittest.TestCase):
    def test_parses_prefix_and_period_with_optional_fetched(self):
        self.assertEqual(
            parse_degiro_export(Path("account_2025-01-05_2026-10-01_2026-10-02.csv")),
            ("account", (date(2025, 1, 5), date(2026, 10, 1))),
        )
        self.assertEqual(
            parse_degiro_export(Path("transactions_2026-08-13_2026-08-17.csv")),
            ("transactions", (date(2026, 8, 13), date(2026, 8, 17))),
        )
        self.assertIsNone(parse_degiro_export(Path("Account.csv")))
        self.assertIsNone(parse_degiro_export(Path("readme.txt")))


class PruneContainedDegiroTests(unittest.TestCase):
    def test_detects_contained_per_prefix_and_skips_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outer = _touch(root, "account_2025-01-05_2026-10-01_2026-10-02.csv")
            inner = _touch(root, "account_2026-08-13_2026-08-17.csv")
            tx_outer = _touch(root, "transactions_2025-01-05_2026-10-01_2026-10-02.csv")
            tx_inner = _touch(root, "transactions_2026-08-13_2026-08-17.csv")
            # Same calendar span as account outer — not compared across kinds.
            _touch(root, "portfolio_2025-01-05_2026-10-01_2026-10-02.csv")
            junk = _touch(root, "notes.txt")

            results = prune_contained_degiro(root, delete=False)
            contained = [r for r in results if r.action == ACTION_CONTAINED]
            skipped = [r for r in results if r.action == ACTION_SKIPPED]

            self.assertEqual({r.path for r in contained}, {inner, tx_inner})
            self.assertEqual(contained[0].covered_by in {outer, tx_outer}, True)
            by_path = {r.path: r for r in contained}
            self.assertEqual(by_path[inner].covered_by, outer)
            self.assertEqual(by_path[tx_inner].covered_by, tx_outer)
            self.assertEqual([r.path for r in skipped], [junk])
            self.assertTrue(inner.is_file())

    def test_does_not_compare_account_with_transactions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch(root, "account_2025-01-01_2025-12-31.csv")
            _touch(root, "transactions_2025-06-01_2025-06-30.csv")

            results = prune_contained_degiro(root, delete=False)
            self.assertEqual([r for r in results if r.action == ACTION_CONTAINED], [])

    def test_delete_removes_only_contained(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outer = _touch(root, "account_2025-01-05_2026-10-01.csv")
            inner = _touch(root, "account_2026-08-13_2026-08-17.csv")

            results = prune_contained_degiro(root, delete=True)
            deleted = [r for r in results if r.action == ACTION_DELETED]
            self.assertEqual(len(deleted), 1)
            self.assertEqual(deleted[0].path, inner)
            self.assertFalse(inner.exists())
            self.assertTrue(outer.is_file())

    def test_gaps_after_dropping_contained(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch(root, "account_2020-01-01_2020-02-28.csv")
            _touch(root, "account_2020-02-10_2020-02-20.csv")  # contained
            _touch(root, "account_2020-03-15_2020-06-30.csv")

            gaps = find_degiro_gaps(root / "p_degiro")
            self.assertEqual(len(gaps), 1)
            self.assertEqual(gaps[0].kind, "account")
            self.assertEqual(gaps[0].gap, (date(2020, 2, 29), date(2020, 3, 14)))

            audit = audit_degiro_statements(root, delete=False)
            self.assertEqual(len([r for r in audit.contained if r.action == ACTION_CONTAINED]), 1)
            self.assertEqual(len(audit.gaps), 1)


if __name__ == "__main__":
    unittest.main()
