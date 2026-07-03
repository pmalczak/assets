import unittest
import importlib
# import sys
# import types
from pathlib import Path
from unittest.mock import patch

import pandas as pd


# data_step_package = types.ModuleType("data_step")
# data_step_module = types.ModuleType("data_step.data_step")
# data_step_module.DATA_STEP = object()
# data_step_package.data_step = data_step_module
# sys.modules.setdefault("data_step", data_step_package)
# sys.modules.setdefault("data_step.data_step", data_step_module)

# nbp_fx_package = types.ModuleType("nbp_fx_repo")
# nbp_fx_module = types.ModuleType("nbp_fx_repo.nbp_fx_repository")
# nbp_fx_module.NBP_API_EUR = "eur"
# nbp_fx_package.nbp_fx_repository = nbp_fx_module
# sys.modules.setdefault("nbp_fx_repo", nbp_fx_package)
# sys.modules.setdefault("nbp_fx_repo.nbp_fx_repository", nbp_fx_module)

build_portfolio_history = importlib.import_module("portfolio_history").build_portfolio_history


class BuildPortfolioHistoryTests(unittest.TestCase):
    def test_builds_daily_history_with_group_aggregation_and_fx(self):
        assets_catalog = pd.DataFrame(
            [
                {"id": "acc_pln", "RODZAJ*": "mbank.PM"},
                {"id": "acc_eur", "RODZAJ*": "revolut.PM"},
            ]
        )
        fx_rates = pd.DataFrame(
            {"eur": [4.0, 4.1, 4.2]},
            index=pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03"]),
        )

        histories = [
            pd.DataFrame(
                [
                    {
                        "asset_key": "acc_pln",
                        "group": "1 konta bankowe",
                        "date": pd.Timestamp("2025-01-01"),
                        "value": 100.0,
                        "currency": "PLN",
                    },
                    {
                        "asset_key": "acc_pln",
                        "group": "1 konta bankowe",
                        "date": pd.Timestamp("2025-01-03"),
                        "value": 130.0,
                        "currency": "PLN",
                    },
                ]
            ),
            pd.DataFrame(
                [
                    {
                        "asset_key": "acc_eur",
                        "group": "5 inwestycje finansowe",
                        "date": pd.Timestamp("2025-01-02"),
                        "value": 10.0,
                        "currency": "EUR",
                    }
                ]
            ),
        ]

        # with (
        #     # patch("portfolio_history.get_online_data_root", return_value=Path("C:/fake")),
        #     patch("portfolio_history._build_asset_history", side_effect=histories),
        # ):
        result = build_portfolio_history(
            assets_catalog,
            fx_rates,
            end_date=pd.Timestamp("2025-01-03"),
            days=3,
        )

        history = result["history"].sort_values(["date", "group"]).reset_index(drop=True)
        expected = pd.DataFrame(
            [
                {"date": pd.Timestamp("2025-01-01"), "group": "1 konta bankowe", "value_pln": 100.0},
                {"date": pd.Timestamp("2025-01-01"), "group": "5 inwestycje finansowe", "value_pln": 0.0},
                {"date": pd.Timestamp("2025-01-02"), "group": "1 konta bankowe", "value_pln": 100.0},
                {"date": pd.Timestamp("2025-01-02"), "group": "5 inwestycje finansowe", "value_pln": 41.0},
                {"date": pd.Timestamp("2025-01-03"), "group": "1 konta bankowe", "value_pln": 130.0},
                {"date": pd.Timestamp("2025-01-03"), "group": "5 inwestycje finansowe", "value_pln": 42.0},
            ]
        )

        pd.testing.assert_frame_equal(history, expected)
        self.assertEqual(result["supported_assets"], ["acc_pln: mbank.PM", "acc_eur: revolut.PM"])
        self.assertEqual(result["skipped_assets"], [])

    def test_collects_skipped_assets_for_missing_kind_errors_and_empty_histories(self):
        assets_catalog = pd.DataFrame(
            [
                {"id": "no_kind", "RODZAJ*": pd.NA},
                {"id": "broken", "RODZAJ*": "mbank.PM"},
                {"id": "empty", "RODZAJ*": "assets.cash"},
            ]
        )
        fx_rates = pd.DataFrame(
            {"eur": [4.0]},
            index=pd.to_datetime(["2025-01-01"]),
        )

        with (
            patch("portfolio_history.get_online_data_root", return_value=Path("C:/fake")),
            patch(
                "portfolio_history._build_asset_history",
                side_effect=[
                    ValueError("boom"),
                    pd.DataFrame(columns=["asset_key", "group", "date", "value", "currency"]),
                ],
            ),
        ):
            result = build_portfolio_history(
                assets_catalog,
                fx_rates,
                end_date=pd.Timestamp("2025-01-01"),
                days=1,
            )

        self.assertTrue(result["history"].empty)
        self.assertEqual(result["supported_assets"], [])
        self.assertEqual(
            result["skipped_assets"],
            [
                "no_kind: missing kind",
                "broken: mbank.PM (boom)",
                "empty: assets.cash (no history rows)",
            ],
        )


if __name__ == "__main__":
    unittest.main()
