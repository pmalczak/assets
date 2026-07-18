import unittest
from pathlib import Path

from data_step.data_step import DATA_STEP
from analyse_assets.accounts_pools import load_mbank_pool


class MyTestCase(unittest.TestCase):
    def test_something(self):
        local_data_steps_root = Path(__file__).parent.parent
        DATA_STEP.init_steps(root=local_data_steps_root)
        x = load_mbank_pool()
        self.assertEqual(True, False)  # add assertion here


if __name__ == '__main__':
    unittest.main()
