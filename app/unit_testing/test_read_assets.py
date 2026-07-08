import unittest
from pathlib import Path

from importers.assets.data_model import AssetsFile
from importers.assets.read_assets import read_assets
from data_step.data_step import DATA_STEP


class MyTestCase(unittest.TestCase):
    def test_something(self):
        local_data_steps_root = Path(__file__)
        DATA_STEP.init_steps(root=local_data_steps_root)
        df = read_assets()
        self.assertTrue(len(df) > 0)

        x = df[AssetsFile.CURRENCY].unique().tolist()
        self.assertEqual(x, ['PLN', 'EUR'])


if __name__ == '__main__':
    unittest.main()
