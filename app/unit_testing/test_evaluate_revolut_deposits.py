# test_evaluate_deposits.py
import unittest
import pandas as pd

from evaluators.eveluate_revolut_deposits import evaluate_revolut_deposits
from importers.assets.data_model import AssetsDef
from importers.revolut.account_data_model import RevolutAccountFile


class EvaluateDepositsTests(unittest.TestCase):
    assets_file_row = pd.Series({'id': 'xxx'})

    def test_only_deposits_no_withdrawals(self):
        """
        Zakładanie lokat: brak wypłat -> każdy 'Depositing savings' tworzy jeden rekord otwarcia.
        """
        df = pd.DataFrame([
            {RevolutAccountFile.DESCRIPTION: "Depositing savings", RevolutAccountFile.AMOUNT: -100.0, RevolutAccountFile.DATE: "2025-01-10"},
            {RevolutAccountFile.DESCRIPTION: "Depositing savings", RevolutAccountFile.AMOUNT: -50.0, RevolutAccountFile.DATE: "2025-02-01"},
        ])

        res = evaluate_revolut_deposits(df, self.assets_file_row, product='lokata',
                                        depositing_selector='Depositing savings', withdrowing_selector='Withdrawal savings')

        # 2 otwarcia, brak zamknięć
        self.assertEqual(len(res), 2)
        # Weryfikacja wartości i dat
        self.assertEqual(res[0][AssetsDef.VALUE], 100.0)
        self.assertEqual(res[0][AssetsDef.EVALUATION_DATE], "2025-01-10")
        self.assertEqual(res[0][AssetsDef.GROUP], '2 depozyty')
        self.assertEqual(res[0][AssetsDef.TYPE], "investment.depozyt")
        self.assertIn("otwarcie", res[0][AssetsDef.DESCR])

        self.assertEqual(res[1][AssetsDef.VALUE], 50.0)
        self.assertEqual(res[1][AssetsDef.EVALUATION_DATE], "2025-02-0"
                                                            "1")
        self.assertIn("otwarcie", res[1][AssetsDef.DESCR])

    def test_withdrawal_exhausts_at_least_one_deposit(self):
        """
        Wypłata wyczerpuje co najmniej jedną lokatę (FIFO).
        Przykład: depozyty 100 i 50, wypłata 120 -> zamyka 100 w całości i 20 z drugiej.
        """
        df = pd.DataFrame([
            {RevolutAccountFile.DESCRIPTION: "Depositing savings", RevolutAccountFile.AMOUNT: -100.0, RevolutAccountFile.DATE: "2025-01-10"},
            {RevolutAccountFile.DESCRIPTION: "Depositing savings", RevolutAccountFile.AMOUNT: -50.0, RevolutAccountFile.DATE: "2025-02-01"},
            {RevolutAccountFile.DESCRIPTION: "Withdrawal savings", RevolutAccountFile.AMOUNT: 120.0, RevolutAccountFile.DATE: "2025-03-01"},
        ])

        res = evaluate_revolut_deposits(df, self.assets_file_row, product='lokata',
                                        depositing_selector='Depositing savings', withdrowing_selector='Withdrawal savings')

        # Oczekujemy: 2 otwarcia + 2 zamknięcia (100 + 20)
        self.assertEqual(len(res), 4)

        opens = [r for r in res if r[AssetsDef.VALUE] > 0]
        closes = [r for r in res if r[AssetsDef.VALUE] < 0]
        self.assertEqual(len(opens), 2)
        self.assertEqual(len(closes), 2)

        # Suma zamknięć = -120
        total_close = sum(r[AssetsDef.VALUE] for r in closes)
        self.assertAlmostEqual(total_close, -120.0, places=8)

        # FIFO: pierwsze zamknięcie powinno odpowiadać pierwszej dacie otwarcia
        self.assertIn("2025-01-10", closes[0][AssetsDef.DESCR])

    def test_withdrawal_exceeds_total_deposits_interest_case(self):
        """
        Wypłata > suma wpłat (reprezentuje naliczenie odsetek).
        Algorytm ignoruje nadwyżkę ponad sumę lokat i nie rzuca błędu.
        """
        df = pd.DataFrame([
            {RevolutAccountFile.DESCRIPTION: "Depositing savings", RevolutAccountFile.AMOUNT: -100.0, RevolutAccountFile.DATE: "2025-01-10"},
            {RevolutAccountFile.DESCRIPTION: "Depositing savings", RevolutAccountFile.AMOUNT: -50.0, RevolutAccountFile.DATE: "2025-02-01"},
            {RevolutAccountFile.DESCRIPTION: "Withdrawal savings", RevolutAccountFile.AMOUNT: 200.0, RevolutAccountFile.DATE: "2025-03-01"},  # > 150
        ])

        res = evaluate_revolut_deposits(df, self.assets_file_row, product='lokata',
                                        depositing_selector='Depositing savings', withdrowing_selector='Withdrawal savings')

        # Oczekujemy: 2 otwarcia + 2 zamknięcia (zamknięcia łącznie = -150, nadwyżka 50 ignorowana)
        self.assertEqual(len(res), 4)

        opens = [r for r in res if r[AssetsDef.VALUE] > 0]
        closes = [r for r in res if r[AssetsDef.VALUE] < 0]
        self.assertEqual(len(opens), 2)
        self.assertEqual(len(closes), 2)

        total_deposited = sum(r[AssetsDef.VALUE] for r in opens)
        total_closed = -sum(r[AssetsDef.VALUE] for r in closes)  # dodatnia liczba zamknięć
        self.assertAlmostEqual(total_deposited, 150.0, places=8)
        self.assertAlmostEqual(total_closed, 150.0, places=8)

        # Ostatnie zamknięcie powinno dotyczyć drugiego (młodszego) depozytu
        self.assertIn("2025-02-01", closes[-1][AssetsDef.DESCR])


if __name__ == "__main__":
    # Pozwala uruchomić ten plik samodzielnie (python -m nose2 lub python test_evaluate_deposits.py)
    unittest.main()
