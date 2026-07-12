import unittest

import pandas as pd

from app_proc.transaction_search import search_transactions


class SearchTransactionsTests(unittest.TestCase):
    def _sample_transactions(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "asset_id": "g_m_23_9039",
                    "asset_opis": "konto glowne",
                    "zrodlo": "mbank",
                    "data": "2026-01-10",
                    "kwota": -100.0,
                    "saldo": 5000.0,
                    "opis": "ZAKUP PRZY UZYCIU KARTY",
                    "tytul": "BIEDRONKA 1234",
                    "kontrahent": "JAN KOWALSKI",
                    "konto": "PL00112233445566778899001122",
                    "dopasowane_pola": "",
                },
                {
                    "asset_id": "p_re_eur",
                    "asset_opis": "revolut eur",
                    "zrodlo": "revolut-konto",
                    "data": "2026-01-11",
                    "kwota": 50.0,
                    "saldo": 200.0,
                    "opis": "Transfer from savings",
                    "tytul": "Transfer",
                    "kontrahent": "Main",
                    "konto": "",
                    "dopasowane_pola": "",
                },
            ]
        )

    def test_search_finds_match_in_kontrahent(self):
        result = search_transactions(self._sample_transactions(), "KOWALSKI")
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["asset_id"], "g_m_23_9039")
        self.assertIn("kontrahent", result.iloc[0]["dopasowane_pola"])

    def test_search_finds_match_in_opis(self):
        result = search_transactions(self._sample_transactions(), "transfer")
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["zrodlo"], "revolut-konto")
        self.assertIn("opis", result.iloc[0]["dopasowane_pola"])

    def test_search_empty_query_returns_no_rows(self):
        result = search_transactions(self._sample_transactions(), "   ")
        self.assertTrue(result.empty)

    def test_search_case_insensitive_by_default(self):
        result = search_transactions(self._sample_transactions(), "biedronka")
        self.assertEqual(len(result), 1)
        self.assertIn("tytul", result.iloc[0]["dopasowane_pola"])
