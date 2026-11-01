import unittest
import tempfile
from pathlib import Path

from importers.revolut.read_r_transactions import _extract_file_date, _read_revolut_account_transactions


ACCOUNT_HEADER = "Rodzaj,Produkt,Data rozpoczęcia,Data zrealizowania,Opis,Kwota,Opłata,Waluta,State,Saldo\n"
ACCOUNT_ROW = 'Transfer,,2026-01-01 00:00:00,2026-01-02 00:00:00,Test,10,0,EUR,ZAKOŃCZONO,10\n'


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

    def test_read_account_ignores_old_subdirectory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            active = root / "account-statement_2026-01-01_2026-01-31_pl-pl_ok.csv"
            active.write_text(ACCOUNT_HEADER + ACCOUNT_ROW, encoding="utf-8")
            old = root / "old"
            old.mkdir()
            (old / "account-statement_2025-01-01_2025-01-31_pl-pl_old.csv").write_text(
                "Completed Date,Product name,Description,Money out,Money in,Balance\n",
                encoding="utf-8",
            )

            df = _read_revolut_account_transactions(root)
            self.assertEqual(len(df), 1)

    def test_read_merges_noncontiguous_periods_regardless_of_glob_order(self):
        """Plik późniejszy w globie, ale wcześniejszy okres — nie może padać na dedupe."""
        row_early = (
            "Transfer,,2026-01-10 00:00:00,2026-01-10 00:00:00,Early,10,0,PLN,ZAKOŃCZONO,10\n"
        )
        row_late = (
            "Transfer,,2026-10-10 00:00:00,2026-10-10 00:00:00,Late,20,0,PLN,ZAKOŃCZONO,30\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Nazwy tak, by niesortowany glob często brał październik przed styczniem.
            (root / "account-statement_2026-10-01_2026-10-31_pl-pl_zzz.csv").write_text(
                ACCOUNT_HEADER + row_late, encoding="utf-8"
            )
            (root / "account-statement_2026-01-01_2026-01-31_pl-pl_aaa.csv").write_text(
                ACCOUNT_HEADER + row_early, encoding="utf-8"
            )

            df = _read_revolut_account_transactions(root)
            self.assertEqual(len(df), 2)
            self.assertEqual(df["Opis"].tolist(), ["Early", "Late"])


if __name__ == "__main__":
    unittest.main()

