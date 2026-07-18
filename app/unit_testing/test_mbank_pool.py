import unittest
from unittest.mock import patch

import pandas as pd

from analyse_assets.account_tx import AccountTx
from analyse_assets.accounts_pools import load_accounts_pool
from importers.assets.data_model import AssetsFile, KindDomain, TypeDomain
from importers.assets.pool_id import MBANK_EUR, MBANK_PLN, POOL_ID_COLUMN
from importers.mbank.data_model import MBankFile, MbankOperationType


class LoadAccountsPoolTests(unittest.TestCase):
    def test_unknown_pool_id_raises(self):
        with self.assertRaises(ValueError):
            load_accounts_pool("not_a_pool")

    @patch("analyse_assets.accounts_pools.read_m_transactions")
    @patch("analyse_assets.accounts_pools.read_assets")
    def test_load_mbank_eur_returns_account_tx(self, mock_assets, mock_read):
        mock_assets.return_value = pd.DataFrame(
            [
                {
                    AssetsFile.ID: "g_m_56_3217_eur",
                    AssetsFile.TYPE: TypeDomain.CURRENT_ACCOUNT,
                    AssetsFile.KIND: KindDomain.MBANK + ".GM",
                    AssetsFile.CURRENCY: "EUR",
                    POOL_ID_COLUMN: MBANK_EUR,
                }
            ]
        )
        mock_read.return_value = pd.DataFrame(
            [
                {
                    MBankFile.MBANK_TRANSACTION_DATE: "2022-04-28",
                    MBankFile.MBANK_DESCRIPTION: MbankOperationType.PRZELEW_SEPA_PRZYCHODZACY,
                    MBankFile.MBANK_TITLE: "DYWIDENDA",
                    MBankFile.MBANK_TRANSACTION_PARTY: "GPM",
                    MBankFile.MBANK_ACCOUNT_NUMBER: "",
                    MBankFile.MBANK_AMOUNT: 100.0,
                    MBankFile.MBANK_OUTSTANDING_BALANCE: 100.0,
                }
            ]
        )
        df = load_accounts_pool(MBANK_EUR)
        self.assertFalse(df.empty)
        self.assertIn(AccountTx.OPERATION_TYPE, df.columns)
        self.assertEqual(df.iloc[0][AccountTx.POOL_ID], MBANK_EUR)
        self.assertEqual(df.iloc[0][AccountTx.ACCOUNT_ID], "g_m_56_3217_eur")
        self.assertNotIn(MBankFile.MBANK_DESCRIPTION, df.columns)

    @patch("analyse_assets.accounts_pools.read_revolut_account_transactions")
    @patch("analyse_assets.accounts_pools.read_assets")
    def test_load_revolut_pln_returns_account_tx(self, mock_assets, mock_read):
        from importers.revolut.account_data_model import RevolutAccountFile
        from importers.assets.pool_id import REVOLUT_PLN

        mock_assets.return_value = pd.DataFrame(
            [
                {
                    AssetsFile.ID: "p_re_pln",
                    AssetsFile.TYPE: TypeDomain.CURRENT_ACCOUNT,
                    AssetsFile.KIND: KindDomain.REVOLUT + ".PM",
                    AssetsFile.CURRENCY: "PLN",
                    POOL_ID_COLUMN: REVOLUT_PLN,
                }
            ]
        )
        mock_read.return_value = pd.DataFrame(
            [
                {
                    RevolutAccountFile.DATE: "2021-01-01",
                    RevolutAccountFile.KIND: "Card payment",
                    RevolutAccountFile.DESCRIPTION: "Shop",
                    RevolutAccountFile.PRODUCT: "Current",
                    RevolutAccountFile.AMOUNT: -12.5,
                    RevolutAccountFile.BALANCE: 50.0,
                }
            ]
        )
        df = load_accounts_pool(REVOLUT_PLN)
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0][AccountTx.OPERATION_TYPE], "Card payment")
        self.assertEqual(df.iloc[0][AccountTx.POOL_ID], REVOLUT_PLN)


if __name__ == "__main__":
    unittest.main()
