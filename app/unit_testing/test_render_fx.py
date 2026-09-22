import unittest
from unittest.mock import patch

import pandas as pd

from app_streamlit.render_fx import (
    CHART_HEIGHT,
    GOLD_COL,
    GOLD_UNIT,
    RATE_COL,
    _load_gold_window,
    build_fx_chart,
)
from nbp_pl_api.nbp_gold_fetch import NBP_GOLD_DATE, NBP_GOLD_PRICE
from roi.gold_terminal import TROY_OUNCE_GRAMS


def _y_encodings(node: dict) -> list[dict]:
    found = []
    encoding = node.get("encoding") or {}
    if "y" in encoding:
        found.append(encoding["y"])
    for child in node.get("layer") or []:
        found.extend(_y_encodings(child))
    return found


class FxGoldChartTests(unittest.TestCase):
    def test_gold_uses_independent_right_axis(self):
        eur = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-08-03", "2026-09-01"]),
                RATE_COL: [4.25, 4.30],
            }
        )
        gold = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-08-03", "2026-09-01"]),
                GOLD_COL: [480.0, 530.0],
            }
        )
        month_lines = pd.DataFrame({"date": pd.to_datetime(["2026-09-01"])})

        spec = build_fx_chart(eur, gold, month_lines).to_dict()

        self.assertEqual(spec["resolve"]["scale"]["y"], "independent")
        self.assertEqual(spec["height"], CHART_HEIGHT)
        y_axes = [axis for axis in _y_encodings(spec) if axis.get("title")]
        self.assertEqual(len(y_axes), 2)
        titles = [axis["title"] for axis in y_axes]
        self.assertIn("EUR/PLN", titles)
        self.assertIn(f"Złoto {GOLD_UNIT}", titles)
        gold_axis = next(axis for axis in y_axes if axis["title"] == f"Złoto {GOLD_UNIT}")
        self.assertEqual(gold_axis["axis"]["orient"], "right")

    def test_gold_window_converts_grams_to_troy_ounces(self):
        series = pd.DataFrame(
            {
                NBP_GOLD_DATE: pd.to_datetime(["2026-09-01"]),
                NBP_GOLD_PRICE: [100.0],
            }
        )
        with patch("app_streamlit.render_fx.fetch_nbp_gold", return_value=series):
            out = _load_gold_window("2026-09-01", "2026-09-01")
        self.assertAlmostEqual(float(out[GOLD_COL].iloc[0]), 100.0 * TROY_OUNCE_GRAMS)

    def test_eur_only_when_gold_missing(self):
        eur = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-09-01"]),
                RATE_COL: [4.25],
            }
        )
        spec = build_fx_chart(eur, pd.DataFrame(), pd.DataFrame()).to_dict()
        self.assertNotIn("resolve", spec)
        self.assertEqual(spec["height"], CHART_HEIGHT)
        self.assertEqual(len(spec["layer"]), 1)
        self.assertEqual(spec["layer"][0]["encoding"]["y"]["title"], "EUR/PLN")


if __name__ == "__main__":
    unittest.main()
