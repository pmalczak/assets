import unittest
from unittest.mock import patch

import pandas as pd

from app_streamlit.render_fx import (
    CHART_HEIGHT,
    GOLD_COL,
    GOLD_UNIT,
    INSTRUMENT_COL,
    RATE_COL,
    _load_gold_purchases,
    _load_gold_window,
    build_fx_chart,
)
from importers.assets.data_model import UnitPriceEvaluation
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


def _mark_types(spec: dict) -> list[str]:
    marks = []
    for child in spec.get("layer") or []:
        mark = child.get("mark")
        if isinstance(mark, dict):
            marks.append(mark.get("type"))
        else:
            marks.append(mark)
    return marks


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
        # Płaskie warstwy: rule + EUR + złoto (bez zagnieżdżonego layer).
        self.assertEqual(len(spec["layer"]), 3)
        self.assertFalse(any("layer" in child for child in spec["layer"]))
        y_axes = [axis for axis in _y_encodings(spec) if axis.get("title")]
        self.assertEqual(len(y_axes), 2)
        titles = [axis["title"] for axis in y_axes]
        self.assertIn("EUR/PLN", titles)
        self.assertIn(f"Złoto {GOLD_UNIT}", titles)
        eur_axis = next(axis for axis in y_axes if axis["title"] == "EUR/PLN")
        self.assertEqual(eur_axis["axis"]["orient"], "left")
        gold_axis = next(axis for axis in y_axes if axis["title"] == f"Złoto {GOLD_UNIT}")
        self.assertEqual(gold_axis["axis"]["orient"], "right")

    def test_purchases_share_gold_axis(self):
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
        purchases = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-08-15"]),
                GOLD_COL: [510.0],
                INSTRUMENT_COL: ["Krugerrand"],
            }
        )
        spec = build_fx_chart(eur, gold, pd.DataFrame(), purchases).to_dict()
        self.assertEqual(len(spec["layer"]), 3)  # EUR + gold line + points
        self.assertIn("point", _mark_types(spec))
        # Jedna widoczna prawa oś (linia); punkty bez axis, ale ten sam domain.
        titled = [y for y in _y_encodings(spec) if y.get("title") == f"Złoto {GOLD_UNIT}"]
        self.assertEqual(len(titled), 1)
        self.assertEqual(titled[0]["axis"]["orient"], "right")
        right_domains = [
            layer["encoding"]["y"]["scale"]["domain"]
            for layer in spec["layer"]
            if layer.get("encoding", {}).get("y", {}).get("field") == GOLD_COL
        ]
        self.assertEqual(len(right_domains), 2)
        self.assertEqual(right_domains[0], right_domains[1])
        self.assertLessEqual(right_domains[0][0], 480.0)
        self.assertGreaterEqual(right_domains[0][1], 530.0)

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

    def test_load_gold_purchases_filters_window(self):
        raw = pd.DataFrame(
            {
                UnitPriceEvaluation.DATE: pd.to_datetime(
                    ["2026-07-01", "2026-08-15", "2026-10-01"]
                ),
                UnitPriceEvaluation.UNIT_PRICE: [400.0, 510.0, 600.0],
                UnitPriceEvaluation.INSTRUMENT: ["A", "B", "C"],
                UnitPriceEvaluation.NOTES: [None, None, None],
            }
        )
        with patch(
            "app_streamlit.render_fx.read_unit_price_evaluation", return_value=raw
        ):
            out = _load_gold_purchases("2026-08-01", "2026-09-30", 1.0)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[INSTRUMENT_COL].iloc[0], "B")
        self.assertAlmostEqual(float(out[GOLD_COL].iloc[0]), 510.0)

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
        eur_y = spec["layer"][0]["encoding"]["y"]
        self.assertEqual(eur_y["title"], "EUR/PLN")
        self.assertEqual(eur_y["axis"]["orient"], "left")


if __name__ == "__main__":
    unittest.main()
