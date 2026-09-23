import tempfile
import unittest
from pathlib import Path

from maintenance.move_downloaded_results import ACTION_MOVED, KIND_MBANK
from maintenance.move_mbank_files import (
    account_key_from_stem,
    get_target_dirs,
    move_mbank_files,
)


class MoveMbankFilesTests(unittest.TestCase):
    def test_account_key_from_stem(self):
        self.assertEqual(account_key_from_stem("12344448_20240101_20240201"), "4448")

    def test_get_target_dirs_uses_fourth_segment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "p_m_23_2330").mkdir()
            (root / "g_m_56_3217_eur").mkdir()
            (root / "ignored").mkdir()
            self.assertEqual(
                get_target_dirs(root),
                {"2330": "p_m_23_2330", "3217": "g_m_56_3217_eur"},
            )

    def test_moves_matching_account(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            download = root / "Downloads"
            cash_pool = root / "cash_pool"
            download.mkdir()
            (cash_pool / "p_m_12_4448").mkdir(parents=True)
            # stem 22 znaki: 8 + '_' + 6 + '_' + 6
            src = download / "abcd4448_240101_240201.csv"
            src.write_text("x", encoding="utf-8")
            self.assertEqual(len(src.stem), 22)

            results = move_mbank_files(cash_pool, download)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].action, ACTION_MOVED)
            self.assertEqual(results[0].kind, KIND_MBANK)
            self.assertFalse(src.exists())
            self.assertTrue((cash_pool / "p_m_12_4448" / src.name).is_file())

    def test_unknown_account_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            download = root / "Downloads"
            cash_pool = root / "cash_pool"
            download.mkdir()
            (cash_pool / "p_m_23_2330").mkdir(parents=True)
            src = download / "abcd4448_240101_240201.csv"
            src.write_text("x", encoding="utf-8")
            self.assertEqual(len(src.stem), 22)

            with self.assertRaises(ValueError) as ctx:
                move_mbank_files(cash_pool, download)

            msg = str(ctx.exception)
            self.assertIn("4448", msg)
            self.assertIn("2330", msg)
            self.assertIn(src.name, msg)
            self.assertTrue(src.is_file())
