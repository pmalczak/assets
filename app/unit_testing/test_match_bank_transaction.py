import unittest

import pandas as pd

from importers.assets.data_model import PurchaseRules, TitleMatchDomain
from importers.assets.match_bank_transaction import match_purchase_rules


class MatchBankTransactionTests(unittest.TestCase):
    def _transactions(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "date": pd.Timestamp("2024-03-15"),
                    "title": "ZAKUP MONET MENNICA",
                    "counterparty": "MENNICA KAPITALOWA",
                    "counterparty_account": "PL61102010260000042270201111",
                    "amount": -15000.0,
                    "operation_description": "PRZELEW ZEWNĘTRZNY WYCHODZĄCY",
                },
                {
                    "date": pd.Timestamp("2024-03-15"),
                    "title": "ZAKUP MONET MENNICA",
                    "counterparty": "MENNICA KAPITALOWA",
                    "counterparty_account": "PL61102010260000042270201111",
                    "amount": -15000.0,
                    "operation_description": "PRZELEW ZEWNĘTRZNY WYCHODZĄCY",
                },
            ]
        )

    def _rule(self, **overrides) -> pd.DataFrame:
        row = {
            PurchaseRules.RULE_ID: "km-2024-03",
            PurchaseRules.SOURCE_ACCOUNT: "p_m_34_9142",
            PurchaseRules.DATE: pd.Timestamp("2024-03-15"),
            PurchaseRules.DATE_FROM: pd.NA,
            PurchaseRules.DATE_TO: pd.NA,
            PurchaseRules.TITLE: "MENNICA",
            PurchaseRules.TITLE_MATCH: TitleMatchDomain.CONTAINS,
            PurchaseRules.COUNTERPARTY: "MENNICA",
            PurchaseRules.COUNTERPARTY_IBAN: "PL61102010260000042270201111",
            PurchaseRules.AMOUNT: -15000.0,
            PurchaseRules.AMOUNT_TOLERANCE: 0.01,
            PurchaseRules.OPERATION_DESCRIPTION: "PRZELEW ZEWNĘTRZNY WYCHODZĄCY",
            PurchaseRules.INSTRUMENT: "Krugerrand 1oz",
            PurchaseRules.QUANTITY: 1,
            PurchaseRules.WEIGHT: "1oz",
            PurchaseRules.NOTES: "",
        }
        row.update(overrides)
        return pd.DataFrame([row])

    def test_single_match_is_ok(self):
        tx = self._transactions().iloc[[0]]
        outcomes = match_purchase_rules(self._rule(), tx)
        self.assertEqual(outcomes[0].status, "ok")

    def test_no_match_is_reported(self):
        outcomes = match_purchase_rules(
            self._rule(**{PurchaseRules.TITLE: "INNY TYTUL"}),
            self._transactions().iloc[[0]],
        )
        self.assertEqual(outcomes[0].status, "no_match")
        self.assertIn("Brak dopasowania", outcomes[0].message)

    def test_multiple_matches_are_reported(self):
        outcomes = match_purchase_rules(self._rule(), self._transactions())
        self.assertEqual(outcomes[0].status, "multiple_matches")
        self.assertIn("dopasowala 2 transakcji", outcomes[0].message)


if __name__ == "__main__":
    unittest.main()
