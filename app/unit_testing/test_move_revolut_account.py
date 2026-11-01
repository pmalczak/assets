# -*- coding: utf-8 -*-
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from importers.revolut.account_data_model import RevolutAccountFile
from maintenance.move_downloaded_results import ACTION_MOVED
from maintenance.move_revolut_files import move_revolut_files

ACCOUNT_HEADER = (
    "Rodzaj,Produkt,Data rozpoczęcia,Data zrealizowania,Opis,Kwota,Opłata,Waluta,State,Saldo\n"
)

# Skrót fixture multi-waluta (jak download/pm/x/account-statement_…_b7a7a9).
_MULTI_CURRENCY_CSV = (
    ACCOUNT_HEADER
    + "Przelew,Bieżące,2026-10-07 20:33:01,2026-10-07 20:33:01,To Robo portfolio,-5000.00,0.00,EUR,ZAKOŃCZONO,32043.05\n"
    + "Wymiana,Bieżące,2026-10-22 12:08:59,2026-10-22 12:08:59,Wymiana na PLN,-5000.00,0.00,EUR,ZAKOŃCZONO,27043.05\n"
    + "Płatność kartą,Bieżące,2026-10-01 20:24:00,2026-10-02 06:05:09,Biedronka,-187.11,0.00,PLN,ZAKOŃCZONO,7988.80\n"
    + "Płatność kartą,Bieżące,2026-10-01 19:12:19,2026-10-02 06:17:34,Centrum Medyczne OMNI Clinic,-450.00,0.00,PLN,ZAKOŃCZONO,7538.80\n"
    + "Wymiana,Bieżące,2026-10-22 12:08:59,2026-10-22 12:08:59,Wymiana na PLN,21800.00,0.00,PLN,ZAKOŃCZONO,21849.14\n"
)


class MoveAccountStatementTests(unittest.TestCase):
    def _run_move(self, home: Path, filename: str, content: str):
        download = home / "Dropbox" / "INWESTYCJE" / "download" / "pm"
        cash_pool = home / "Dropbox" / "INWESTYCJE" / "cash_pool"
        download.mkdir(parents=True)
        cash_pool.mkdir(parents=True)

        src = download / filename
        src.write_text(content, encoding="utf-8")

        with patch("pathlib.Path.home", return_value=home):
            results = move_revolut_files(cash_pool, "p_re", assets_root=home / "assets")

        return src, cash_pool, results

    def test_mono_currency_renames_to_currency_folder(self):
        row = (
            "Transfer,Bieżące,2026-01-01 00:00:00,2026-01-02 00:00:00,"
            "Test,10,0,EUR,ZAKOŃCZONO,10\n"
        )
        name = "account-statement_2026-01-01_2026-01-31_pl-pl_mono.csv"
        with tempfile.TemporaryDirectory() as tmp:
            src, cash_pool, results = self._run_move(
                Path(tmp), name, ACCOUNT_HEADER + row
            )
            moved = [r for r in results if r.action == ACTION_MOVED]
            self.assertEqual(len(moved), 1)
            self.assertFalse(src.exists())
            dest = cash_pool / "p_re_eur" / name
            self.assertTrue(dest.is_file())
            self.assertEqual(moved[0].destination, dest)

    def test_multi_currency_splits_into_currency_folders(self):
        name = "account-statement_2026-10-01_2026-10-31_pl-pl_b7a7a9.csv"
        with tempfile.TemporaryDirectory() as tmp:
            src, cash_pool, results = self._run_move(
                Path(tmp), name, _MULTI_CURRENCY_CSV
            )
            moved = [r for r in results if r.action == ACTION_MOVED]
            self.assertEqual(len(moved), 2)
            self.assertFalse(src.exists())

            pln = cash_pool / "p_re_pln" / name
            eur = cash_pool / "p_re_eur" / name
            self.assertTrue(pln.is_file())
            self.assertTrue(eur.is_file())

            pln_df = pd.read_csv(pln)
            eur_df = pd.read_csv(eur)
            self.assertEqual(len(eur_df), 2)
            self.assertEqual(len(pln_df), 3)
            self.assertEqual(
                set(eur_df[RevolutAccountFile.CURRENCY].str.upper()), {"EUR"}
            )
            self.assertEqual(
                set(pln_df[RevolutAccountFile.CURRENCY].str.upper()), {"PLN"}
            )


if __name__ == "__main__":
    unittest.main()
