import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from importers.assets.data_model import AssetsDef
from roi.asset_dir import require_asset_dir, require_broker_asset_dir
from roi.eps import MONEY_EPS, QTY_EPS


class EpsConstantsTests(unittest.TestCase):
    def test_qty_vs_money_thresholds(self):
        self.assertEqual(QTY_EPS, 1e-12)
        self.assertEqual(MONEY_EPS, 1e-9)
        self.assertLess(QTY_EPS, MONEY_EPS)
        # qty near QTY_EPS is "open" for broker cycles; money near MONEY_EPS is sold for deposits
        self.assertGreater(1e-11, QTY_EPS)
        self.assertLess(1e-11, MONEY_EPS)


class RequireAssetDirTests(unittest.TestCase):
    def test_missing_directory_raises(self):
        missing = Path("/tmp/definitely-missing-asset-dir-xyz")
        with patch("roi.asset_dir.resolve_asset_dir", return_value=missing):
            with self.assertRaises(ValueError) as ctx:
                require_asset_dir("p_xtb", "investment.udziały")
        self.assertIn("Brak katalogu", str(ctx.exception))

    def test_missing_broker_row_raises(self):
        empty = pd.DataFrame(columns=[AssetsDef.ID, AssetsDef.TYPE])
        with self.assertRaises(ValueError) as ctx:
            require_broker_asset_dir("no_such_broker", assets=empty)
        self.assertIn("Brak aktywa brokerskiego", str(ctx.exception))

    def test_existing_dir_returns_path(self):
        with patch("roi.asset_dir.resolve_asset_dir", return_value=Path("/tmp")):
            # /tmp exists on Linux CI/dev
            path = require_asset_dir("any", "cash_pool.ror")
        self.assertEqual(path, Path("/tmp"))


if __name__ == "__main__":
    unittest.main()
