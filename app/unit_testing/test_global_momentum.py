import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

_SANDBOX = Path(__file__).resolve().parents[1] / "sandbox"
if str(_SANDBOX) not in sys.path:
    sys.path.insert(0, str(_SANDBOX))

from global_momentum_common import last_completed_month_end
from global_momentum_u8_ranking import (
    RANKING_TICKERS,
    annotate_asset_top3_drift,
    compute_current_universe7_ranking,
    last_common_close_date,
    top3_drift_marker,
    with_partial_month_stub,
)


def _monthly_prices(months: int = 24) -> pd.DataFrame:
    end = last_completed_month_end()
    index = pd.date_range(end=end, periods=months, freq="ME")
    data = {}
    for offset, asset in enumerate(RANKING_TICKERS):
        data[asset] = 100 + offset + np.arange(months, dtype=float)
    return pd.DataFrame(data, index=index)


def _universe() -> list[str]:
    return list(RANKING_TICKERS.keys())


class GlobalMomentumRankingTests(unittest.TestCase):
    def test_ready_ranking_has_top3_allocation(self):
        result = compute_current_universe7_ranking(
            _monthly_prices(),
            _universe(),
        )
        self.assertTrue(result["ready"])
        self.assertEqual(len(result["ranking"]), len(RANKING_TICKERS))
        self.assertEqual(
            set(result["ranking"]["Rank"]),
            set(range(1, len(RANKING_TICKERS) + 1)),
        )
        self.assertEqual(len(result["allocation"]), 4)
        self.assertAlmostEqual(float(result["allocation"]["Weight"].sum()), 1.0)

    def test_unavailable_signal_returns_availability(self):
        short = _monthly_prices(months=4)
        result = compute_current_universe7_ranking(short, _universe())
        self.assertFalse(result["ready"])
        self.assertEqual(len(result["availability"]), len(RANKING_TICKERS))
        self.assertIn("Ticker", result["availability"].columns)

    def test_partial_month_stub_changes_ranking(self):
        month_end = _monthly_prices()
        official = compute_current_universe7_ranking(month_end, _universe())
        self.assertTrue(official["ready"])

        stub_date = last_completed_month_end() + pd.Timedelta(days=15)
        stub = month_end.iloc[-1].copy()
        weak_asset = list(RANKING_TICKERS.keys())[-1]
        stub[weak_asset] = stub[weak_asset] * 4
        stub_row = stub.to_frame().T
        stub_row.index = pd.DatetimeIndex([stub_date])
        nowcast_prices = pd.concat([month_end, stub_row])

        as_today = compute_current_universe7_ranking(
            nowcast_prices,
            _universe(),
            as_of_limit=stub_date,
        )
        self.assertTrue(as_today["ready"])
        self.assertEqual(as_today["signal_date"], stub_date.date())
        self.assertNotEqual(
            list(official["ranking"]["Score"]),
            list(as_today["ranking"]["Score"]),
        )

    def test_no_common_close_is_not_ready(self):
        daily = pd.DataFrame(
            {
                asset: pd.Series(
                    [100.0 + i],
                    index=[pd.Timestamp("2026-01-01") + pd.Timedelta(days=i)],
                )
                for i, asset in enumerate(RANKING_TICKERS)
            }
        )
        self.assertIsNone(last_common_close_date(daily))
        monthly, as_of = with_partial_month_stub(_monthly_prices(), daily)
        self.assertTrue(monthly.empty)
        self.assertIsNone(as_of)
        result = compute_current_universe7_ranking(
            monthly,
            _universe(),
            as_of_limit=last_completed_month_end(),
        )
        self.assertFalse(result["ready"])

    def test_as_today_matches_month_end_when_stub_not_after_month_end(self):
        completed = _monthly_prices()
        monthly_stub, as_of = with_partial_month_stub(completed, completed)
        self.assertEqual(as_of, last_completed_month_end())
        pd.testing.assert_frame_equal(monthly_stub, completed)
        official = compute_current_universe7_ranking(completed, _universe())
        as_today = compute_current_universe7_ranking(
            monthly_stub,
            _universe(),
            as_of_limit=as_of,
        )
        pd.testing.assert_frame_equal(official["ranking"], as_today["ranking"])
        self.assertEqual(official["signal_date"], as_today["signal_date"])


class Top3DriftMarkerTests(unittest.TestCase):
    def test_marker_truth_table(self):
        self.assertEqual(top3_drift_marker(was_top=True, is_top=True), "*")
        self.assertEqual(top3_drift_marker(was_top=False, is_top=True), "+")
        self.assertEqual(top3_drift_marker(was_top=True, is_top=False), "-")
        self.assertEqual(top3_drift_marker(was_top=False, is_top=False), ".")

    def test_annotate_prefixes_asset_names(self):
        previous = pd.DataFrame(
            {
                "Asset": ["USA", "Europe", "Japan", "Bonds", "Gold"],
                "TOP3": [True, True, True, False, False],
            }
        )
        current = pd.DataFrame(
            {
                "Asset": ["USA", "Europe", "Bonds", "Japan", "Gold"],
                "TOP3": [True, False, True, False, False],
            }
        )
        annotated = annotate_asset_top3_drift(current, previous)
        self.assertEqual(
            list(annotated["Asset"]),
            ["* USA", "- Europe", "+ Bonds", "- Japan", ". Gold"],
        )


if __name__ == "__main__":
    unittest.main()
