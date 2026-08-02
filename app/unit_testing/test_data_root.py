import unittest
from pathlib import Path
from unittest.mock import patch

from analyse_assets.config_model import CONFIG_FILE_NAME
from app_proc.data_root import A_CONFIG_FILE_NAME, resolve_asset_dir
from importers.assets.read_assets import ASSETS_FILE_NAME


class AConfigFileNameTests(unittest.TestCase):
    def test_assets_and_config_share_a_config_name(self):
        self.assertEqual(A_CONFIG_FILE_NAME, "a_config.xlsx")
        self.assertEqual(ASSETS_FILE_NAME, A_CONFIG_FILE_NAME)
        self.assertEqual(CONFIG_FILE_NAME, A_CONFIG_FILE_NAME)


class ResolveAssetDirTests(unittest.TestCase):
    @patch("app_proc.data_root.get_cash_pool_root")
    @patch("app_proc.data_root.get_online_data_root")
    def test_cash_pool_typ_uses_cash_pool_root(self, assets_root_mock, cash_pool_root_mock):
        assets_root_mock.return_value = Path("/dropbox/INWESTYCJE/assets")
        cash_pool_root_mock.return_value = Path("/dropbox/INWESTYCJE/cash_pool")

        result = resolve_asset_dir("g_m_23_9039", "cash_pool.ror")

        self.assertEqual(result, Path("/dropbox/INWESTYCJE/cash_pool/g_m_23_9039"))
        cash_pool_root_mock.assert_called_once()
        assets_root_mock.assert_not_called()

    @patch("app_proc.data_root.get_cash_pool_root")
    @patch("app_proc.data_root.get_online_data_root")
    def test_investment_typ_uses_assets_root(self, assets_root_mock, cash_pool_root_mock):
        assets_root_mock.return_value = Path("/dropbox/INWESTYCJE/assets")
        cash_pool_root_mock.return_value = Path("/dropbox/INWESTYCJE/cash_pool")

        result = resolve_asset_dir("obligacjeskarbowe", "investment.obligacje")

        self.assertEqual(result, Path("/dropbox/INWESTYCJE/assets/obligacjeskarbowe"))
        assets_root_mock.assert_called_once()
        cash_pool_root_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
