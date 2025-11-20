import unittest
from pathlib import Path

from importers.mbank.read_m_transactions import _read_m_transactions
from importers.mbank.data_model import MBankFile


class MyTestCase(unittest.TestCase):
    def test_something(self):
        source_dir = Path(__file__).parent
        df = _read_m_transactions(source_file=source_dir)
        balance = df[MBankFile.MBANK_AMOUNT].sum()
        outstanding_balance = df[MBankFile.MBANK_OUTSTANDING_BALANCE].sum()
        self.assertAlmostEqual(balance, -208301.76, places=6)
        self.assertAlmostEqual(outstanding_balance, 1224978.17, places=6)
        return

if __name__ == '__main__':
    unittest.main()
