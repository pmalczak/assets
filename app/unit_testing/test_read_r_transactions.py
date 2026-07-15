import unittest
from pathlib import Path

from importers.revolut.read_r_transactions import _extract_file_date


class ExtractRevolutFileDateTests(unittest.TestCase):
    def test_extract_file_date_standard_name(self):
        path = Path("account-statement_2026-01-01_2026-07-15_pl-pl_39cfdd.csv")
        self.assertEqual(_extract_file_date(path), "2026-07-15")

    def test_extract_file_date_with_numeric_suffix(self):
        path = Path("account-statement_2026-01-01_2026-07-14_pl-pl_8a14b9_1.csv")
        self.assertEqual(_extract_file_date(path), "2026-07-14")

    def test_extract_file_date_short_locale(self):
        path = Path("account-statement_2018-08-01_2024-12-31_pl_0733e9.csv")
        self.assertEqual(_extract_file_date(path), "2024-12-31")

    def test_extract_file_date_rejects_invalid_name(self):
        with self.assertRaises(ValueError):
            _extract_file_date(Path("savings-statement_2026-01-01_2026-07-15_pl-pl_1244305841.csv"))


if __name__ == "__main__":
    unittest.main()
