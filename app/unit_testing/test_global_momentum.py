import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

_SANDBOX = Path(__file__).resolve().parents[1] / "sandbox"
if str(_SANDBOX) not in sys.path:
    sys.path.insert(0, str(_SANDBOX))

from global_momentum_common import last_completed_month_end
from global_momentum_u8_ranking import RANKING_TICKERS, compute_current_universe7_ranking


def _monthly_prices(months: int = 24) -> pd.DataFrame:
    end = last_completed_month_end()
    index = pd.date_range(end=end, periods=months, freq="ME")
    data = {}
    for offset, asset in enumerate(RANKING_TICKERS):
        data[asset] = 100 + offset + np.arange(months, dtype=float)
    return pd.DataFrame(data, index=index)


class GlobalMomentumRankingTests(unittest.TestCase):
    def test_ready_ranking_has_top3_allocation(self):
        result = compute_current_universe7_ranking(
            _monthly_prices(),
            list(RANKING_TICKERS.keys()),
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
        result = compute_current_universe7_ranking(short, list(RANKING_TICKERS.keys()))
        self.assertFalse(result["ready"])
        self.assertEqual(len(result["availability"]), len(RANKING_TICKERS))
        self.assertIn("Ticker", result["availability"].columns)


if __name__ == "__main__":
    unittest.main()
