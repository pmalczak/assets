# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from maintenance.prune_contained_statements import (
    ACTION_CONTAINED,
    ACTION_DELETED,
    ACTION_SKIPPED,
    StatementFile,
    find_contained_in_group,
    find_gaps_in_group,
    find_statement_gaps,
    parse_statement_period,
    parse_yymmdd,
    prune_contained_statements,
    statement_kind,
)


def _touch(root: Path, rel: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")
    return path


class ParseStatementPeriodTests(unittest.TestCase):
    def test_mbank_yymmdd(self):
        self.assertEqual(parse_yymmdd("200101"), date(2020, 1, 1))
        self.assertEqual(parse_yymmdd("200331"), date(2020, 3, 31))
        self.assertEqual(
            parse_statement_period(Path("41189039_200101_200331.csv")),
            (date(2020, 1, 1), date(2020, 3, 31)),
        )
        self.assertEqual(statement_kind(Path("41189039_200101_200331.csv")), "mbank:41189039")

    def test_revolut_iso_with_suffix(self):
        path = Path("account-statement_2026-01-01_2026-07-14_pl-pl_8a14b9_1.csv")
        self.assertEqual(parse_statement_period(path), (date(2026, 1, 1), date(2026, 7, 14)))
        self.assertEqual(statement_kind(path), "account-statement")

    def test_savings_and_uuid_skipped(self):
        savings = Path("savings-statement_2025-08-20_2025-12-31_pl-pl_1330814470_d122b5.csv")
        self.assertEqual(parse_statement_period(savings), (date(2025, 8, 20), date(2025, 12, 31)))
        self.assertEqual(statement_kind(savings), "savings-statement")
        uuid_name = Path("8a1fba3b-8f50-4d9b-938b-60b0b98a61e4.csv")
        self.assertIsNone(parse_statement_period(uuid_name))
        self.assertIsNone(statement_kind(uuid_name))


class FindContainedTests(unittest.TestCase):
    def test_inner_period_is_contained(self):
        outer = StatementFile(Path("a_200101_200331.csv"), "mbank:a", date(2020, 1, 1), date(2020, 3, 31))
        inner = StatementFile(Path("a_200201_200331.csv"), "mbank:a", date(2020, 2, 1), date(2020, 3, 31))
        contained = find_contained_in_group([outer, inner])
        self.assertEqual(contained, [(inner, outer)])

    def test_overlap_without_containment_keeps_both(self):
        a = StatementFile(Path("a.csv"), "k", date(2020, 1, 1), date(2020, 3, 31))
        b = StatementFile(Path("b.csv"), "k", date(2020, 2, 1), date(2020, 4, 30))
        self.assertEqual(find_contained_in_group([a, b]), [])

    def test_equal_period_keeps_one_by_name(self):
        keep = StatementFile(Path("aaa.csv"), "k", date(2020, 1, 1), date(2020, 3, 31))
        drop = StatementFile(Path("zzz.csv"), "k", date(2020, 1, 1), date(2020, 3, 31))
        contained = find_contained_in_group([drop, keep])
        self.assertEqual(contained, [(drop, keep)])


class PruneContainedStatementsTests(unittest.TestCase):
    def test_detects_contained_mbank_and_skips_uuid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outer = _touch(root, "g_m_23_9039/41189039_200101_200331.csv")
            inner = _touch(root, "g_m_23_9039/41189039_200201_200331.csv")
            uuid_file = _touch(root, "g_m_23_9039/8a1fba3b-8f50-4d9b-938b-60b0b98a61e4.csv")
            other = _touch(root, "p_m_23_2330/02832330_200201_200331.csv")

            results = prune_contained_statements(root, delete=False)
            contained = [r for r in results if r.action == ACTION_CONTAINED]
            skipped = [r for r in results if r.action == ACTION_SKIPPED]

            self.assertEqual(len(contained), 1)
            self.assertEqual(contained[0].path, inner)
            self.assertEqual(contained[0].covered_by, outer)
            self.assertEqual(contained[0].period, (date(2020, 2, 1), date(2020, 3, 31)))
            self.assertEqual([r.path for r in skipped], [uuid_file])
            self.assertTrue(inner.is_file())
            self.assertTrue(other.is_file())

    def test_does_not_compare_account_with_savings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch(root, "p_re_pln/account-statement_2025-01-01_2025-12-31_pl-pl_aaaaaa.csv")
            _touch(root, "p_re_pln/savings-statement_2025-08-20_2025-12-31_pl-pl_1_2.csv")

            results = prune_contained_statements(root, delete=False)
            self.assertEqual([r for r in results if r.action == ACTION_CONTAINED], [])

    def test_delete_removes_only_contained(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outer = _touch(root, "g_m_23_9039/41189039_200101_200331.csv")
            inner = _touch(root, "g_m_23_9039/41189039_200201_200331.csv")

            results = prune_contained_statements(root, delete=True)
            self.assertEqual(results[0].action, ACTION_DELETED)
            self.assertEqual(results[0].path, inner)
            self.assertFalse(inner.exists())
            self.assertTrue(outer.is_file())


class StatementGapTests(unittest.TestCase):
    def test_gap_between_february_and_mid_march(self):
        first = StatementFile(Path("a_200101_200228.csv"), "mbank:a", date(2020, 1, 1), date(2020, 2, 28))
        second = StatementFile(Path("a_200315_200630.csv"), "mbank:a", date(2020, 3, 15), date(2020, 6, 30))
        gaps = find_gaps_in_group([first, second])
        self.assertEqual(len(gaps), 1)
        gap, before, after = gaps[0]
        self.assertEqual(gap, (date(2020, 2, 29), date(2020, 3, 14)))
        self.assertEqual(before, first)
        self.assertEqual(after, second)

    def test_adjacent_periods_have_no_gap(self):
        a = StatementFile(Path("a.csv"), "k", date(2019, 1, 1), date(2019, 2, 28))
        b = StatementFile(Path("b.csv"), "k", date(2019, 3, 1), date(2019, 6, 30))
        self.assertEqual(find_gaps_in_group([a, b]), [])

    def test_contained_file_does_not_create_false_gap(self):
        outer = StatementFile(Path("wide.csv"), "k", date(2020, 1, 1), date(2020, 6, 30))
        inner = StatementFile(Path("inner.csv"), "k", date(2020, 2, 1), date(2020, 2, 28))
        later = StatementFile(Path("later.csv"), "k", date(2020, 7, 1), date(2020, 8, 31))
        self.assertEqual(find_gaps_in_group([outer, inner, later]), [])

    def test_overlap_bridge_closes_gap(self):
        a = StatementFile(Path("a.csv"), "k", date(2020, 1, 1), date(2020, 2, 28))
        bridge = StatementFile(Path("b.csv"), "k", date(2020, 2, 15), date(2020, 3, 20))
        c = StatementFile(Path("c.csv"), "k", date(2020, 3, 15), date(2020, 6, 30))
        self.assertEqual(find_gaps_in_group([a, bridge, c]), [])

    def test_find_statement_gaps_per_asset_and_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch(root, "g_m_23_9039/41189039_200101_200228.csv")
            _touch(root, "g_m_23_9039/41189039_200315_200630.csv")
            _touch(root, "p_re_pln/account-statement_2025-01-01_2025-01-31_pl-pl_aaaaaa.csv")
            _touch(root, "p_re_pln/savings-statement_2025-03-01_2025-03-31_pl-pl_1_2.csv")

            gaps = find_statement_gaps(root)
            self.assertEqual(len(gaps), 1)
            self.assertEqual(gaps[0].asset_id, "g_m_23_9039")
            self.assertEqual(gaps[0].gap, (date(2020, 2, 29), date(2020, 3, 14)))


if __name__ == "__main__":
    unittest.main()
