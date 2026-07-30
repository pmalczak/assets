import tempfile
import unittest
from pathlib import Path

import pandas as pd

from importers.assets.data_model import AssetsFile
from maintenance.migrate_cash_pool_dirs import migrate_cash_pool_dirs


class MigrateCashPoolDirsTests(unittest.TestCase):
    def test_migrate_moves_cash_pool_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets_root = root / "assets"
            cash_pool_root = root / "cash_pool"
            assets_root.mkdir()
            (assets_root / "g_m_23_9039").mkdir()
            (assets_root / "g_m_23_9039" / "x.csv").write_text("a", encoding="utf-8")
            (assets_root / "obligacje").mkdir()

            assets = pd.DataFrame(
                [
                    {AssetsFile.ID: "g_m_23_9039", AssetsFile.TYPE: "cash_pool.ror"},
                    {AssetsFile.ID: "obligacje", AssetsFile.TYPE: "investment.obligacje"},
                ]
            )

            results = migrate_cash_pool_dirs(
                assets_root=assets_root,
                cash_pool_root=cash_pool_root,
                assets=assets,
                dry_run=False,
            )

            self.assertTrue((cash_pool_root / "g_m_23_9039" / "x.csv").is_file())
            self.assertFalse((assets_root / "g_m_23_9039").exists())
            self.assertTrue((assets_root / "obligacje").is_dir())
            self.assertEqual(results[0].action, "przeniesiony")

    def test_dry_run_does_not_move(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets_root = root / "assets"
            cash_pool_root = root / "cash_pool"
            assets_root.mkdir()
            (assets_root / "p_re_pln").mkdir()

            assets = pd.DataFrame(
                [{AssetsFile.ID: "p_re_pln", AssetsFile.TYPE: "cash_pool.ror"}]
            )

            results = migrate_cash_pool_dirs(
                assets_root=assets_root,
                cash_pool_root=cash_pool_root,
                assets=assets,
                dry_run=True,
            )

            self.assertTrue((assets_root / "p_re_pln").is_dir())
            self.assertFalse(cash_pool_root.exists())
            self.assertEqual(results[0].action, "dry-run (do przeniesienia)")


if __name__ == "__main__":
    unittest.main()
