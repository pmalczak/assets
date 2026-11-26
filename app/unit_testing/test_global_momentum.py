import unittest

import numpy as np
import pandas as pd

from global_momentum.global_momentum_benchmarks import GM_U7_LABEL, prepare_strategy_comparison
from global_momentum.global_momentum_common import display_name, last_completed_month_end
from global_momentum.global_momentum_u8_ranking import (
    RANKING_TICKERS,
    SAFE_RANKING_TICKER,
    annotate_asset_top3_drift,
    annotate_operations_vs_previous,
    build_scoring_normalized_paths,
    compute_current_universe7_ranking,
    last_common_close_date,
    scoring_anchor_label,
    scoring_path_daily_index,
    scoring_path_sample_index,
    top3_drift_marker,
    weight_operation,
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


class ChainLinkPricesTests(unittest.TestCase):
    def test_chain_link_overlaps_timezone_and_intra_month_days(self):
        from global_momentum.global_momentum_common import chain_link_prices

        old = pd.Series(
            [10.0, 11.0, 12.0],
            index=pd.to_datetime(["2024-01-31", "2024-02-29", "2024-03-28"]).tz_localize("America/New_York"),
        )
        new = pd.Series(
            [24.0, 26.0, 28.0],
            index=pd.to_datetime(["2024-02-29", "2024-03-31", "2024-04-30"]).tz_localize("Europe/Berlin"),
        )
        linked = chain_link_prices(old, new, "Safe")
        self.assertGreater(len(linked), 2)
        self.assertEqual(linked.index.min(), pd.Timestamp("2024-01-31"))
        self.assertEqual(linked.index.max(), pd.Timestamp("2024-04-30"))

    def test_chain_link_uses_backfill_when_live_is_empty(self):
        from global_momentum.global_momentum_common import chain_link_prices

        old = pd.Series(
            [10.0, 11.0],
            index=pd.to_datetime(["2024-01-31", "2024-02-29"]),
        )
        linked = chain_link_prices(old, pd.Series(dtype=float), "Safe")
        self.assertEqual(list(linked.values), [10.0, 11.0])


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
        ranking = result["ranking"]
        self.assertIn("Ticker", ranking.columns)
        for asset, ticker in RANKING_TICKERS.items():
            match = ranking.loc[ranking["Asset"] == display_name(asset)]
            self.assertEqual(len(match), 1)
            self.assertEqual(match["Ticker"].iloc[0], ticker)
        allocation = result["allocation"]
        self.assertIn("Ticker", allocation.columns)
        self.assertEqual(allocation.iloc[-1]["Asset"], display_name("Safe"))
        self.assertEqual(allocation.iloc[-1]["Ticker"], SAFE_RANKING_TICKER)

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


class ScoringNormalizedPathsTests(unittest.TestCase):
    def test_t6_is_base_and_markers_match_shift(self):
        monthly = _monthly_prices(months=24)
        asset = next(iter(RANKING_TICKERS))
        signal = monthly.index[-1]
        paths, points = build_scoring_normalized_paths(
            monthly,
            signal_date=signal,
            assets=[asset],
            labels={asset: "A"},
        )
        self.assertFalse(paths.empty)
        self.assertEqual(set(points["Point"]), {"t-12", "t-6", "t-3", "t"})
        by_point = points.set_index("Point")["Level"]
        series = monthly[asset]
        base = float(series.iloc[-7])  # t-6
        self.assertAlmostEqual(float(by_point["t-6"]), 100.0)
        self.assertAlmostEqual(
            float(by_point["t"]),
            float(series.iloc[-1]) / base * 100.0,
        )
        self.assertAlmostEqual(
            float(by_point["t-12"]),
            float(series.iloc[-13]) / base * 100.0,
        )
        self.assertAlmostEqual(
            float(by_point["t-3"]),
            float(series.iloc[-4]) / base * 100.0,
        )
        self.assertEqual(scoring_anchor_label(0), "t")
        self.assertEqual(scoring_anchor_label(12), "t-12")

    def test_path_uses_daily_closes_in_scoring_window(self):
        monthly = _monthly_prices(months=24)
        asset = next(iter(RANKING_TICKERS))
        signal = monthly.index[-1]
        window = monthly.iloc[-13:]
        self.assertEqual(len(scoring_path_sample_index(window.index)), 13)

        daily_index = pd.date_range(window.index.min(), window.index.max(), freq="B")
        daily = pd.DataFrame(
            {asset: np.linspace(90.0, 130.0, len(daily_index))},
            index=daily_index,
        )
        sample_index = scoring_path_daily_index(
            daily,
            start=window.index.min(),
            end=window.index.max(),
            assets=[asset],
        )
        self.assertGreater(len(sample_index), 13)
        self.assertEqual(len(sample_index), len(daily_index))

        paths, points = build_scoring_normalized_paths(
            monthly,
            signal_date=signal,
            assets=[asset],
            labels={asset: "A"},
            daily=daily,
        )
        path_dates = paths["Date"].drop_duplicates()
        self.assertEqual(len(path_dates), len(daily_index))
        self.assertEqual(set(points["Point"]), {"t-12", "t-6", "t-3", "t"})
        mid = sample_index[len(sample_index) // 2]
        mid_level = float(paths.loc[paths["Date"] == mid, "Level"].iloc[0])
        base = float(window.iloc[6][asset])
        expected = float(daily.loc[mid, asset]) / base * 100.0
        self.assertAlmostEqual(mid_level, expected)

    def test_path_falls_back_to_month_ends_without_daily(self):
        monthly = _monthly_prices(months=24)
        asset = next(iter(RANKING_TICKERS))
        paths, points = build_scoring_normalized_paths(
            monthly,
            signal_date=monthly.index[-1],
            assets=[asset],
            labels={asset: "A"},
        )
        self.assertEqual(paths["Date"].nunique(), 13)
        self.assertEqual(set(points["Point"]), {"t-12", "t-6", "t-3", "t"})

    def test_empty_when_history_shorter_than_lookback(self):
        monthly = _monthly_prices(months=8)
        asset = next(iter(RANKING_TICKERS))
        paths, points = build_scoring_normalized_paths(
            monthly,
            signal_date=monthly.index[-1],
            assets=[asset],
        )
        self.assertTrue(paths.empty)
        self.assertTrue(points.empty)


class Top3DriftMarkerTests(unittest.TestCase):
    def test_marker_truth_table(self):
        self.assertEqual(top3_drift_marker(was_top=True, is_top=True), "*")
        self.assertEqual(top3_drift_marker(was_top=False, is_top=True), "+")
        self.assertEqual(top3_drift_marker(was_top=True, is_top=False), "-")
        self.assertEqual(top3_drift_marker(was_top=False, is_top=False), "")

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
            ["* USA", "- Europe", "+ Bonds", "- Japan", "Gold"],
        )


class AllocationOperationTests(unittest.TestCase):
    def test_weight_operation_truth_table(self):
        self.assertEqual(weight_operation(previous=0.0, current=1 / 3), "Buy")
        self.assertEqual(weight_operation(previous=1 / 3, current=0.0), "Sell")
        self.assertEqual(weight_operation(previous=1 / 3, current=1 / 3), "")

    def test_annotate_operations_vs_previous_weights(self):
        previous_allocation = pd.DataFrame(
            {
                "Asset": ["PL", "SXRS", "Japan", "Safe"],
                "Ticker": ["PL.WA", "SXRS.DE", "EUNN.DE", "EXVM.DE"],
                "Weight": [1 / 3, 1 / 3, 1 / 3, 0.0],
            }
        )
        allocation = pd.DataFrame(
            {
                "Asset": ["PL", "SXRS", "Europe", "Safe"],
                "Ticker": ["PL.WA", "SXRS.DE", "EUNK.DE", "EXVM.DE"],
                "Weight": [1 / 3, 0.0, 1 / 3, 1 / 3],
            }
        )
        ranking = pd.DataFrame(
            {
                "Asset": ["PL", "SXRS", "Europe", "Japan", "USA"],
                "Ticker": ["PL.WA", "SXRS.DE", "EUNK.DE", "EUNN.DE", "SXR8.DE"],
                "TOP3": [True, True, True, False, False],
            }
        )
        ranked, allocated = annotate_operations_vs_previous(
            ranking,
            allocation,
            previous_allocation,
        )
        by_ticker = dict(zip(ranked["Ticker"], ranked["Operation"]))
        self.assertEqual(by_ticker["PL.WA"], "")
        self.assertEqual(by_ticker["SXRS.DE"], "Sell")
        self.assertEqual(by_ticker["EUNK.DE"], "Buy")
        self.assertEqual(by_ticker["EUNN.DE"], "Sell")
        self.assertEqual(by_ticker["SXR8.DE"], "")
        safe_op = allocated.loc[allocated["Ticker"] == "EXVM.DE", "Operation"].iloc[0]
        self.assertEqual(safe_op, "Buy")


class StrategyComparisonPrepareTests(unittest.TestCase):
    def test_keeps_gm_u7_column(self):
        raw = pd.DataFrame({GM_U7_LABEL: {"CAGR": 0.08}})
        prepared = prepare_strategy_comparison(raw)
        self.assertIn(GM_U7_LABEL, prepared.columns)
        self.assertAlmostEqual(prepared.loc["CAGR", GM_U7_LABEL], 0.08)

    def test_transposes_when_gm_u7_is_index(self):
        raw = pd.DataFrame({"CAGR": {GM_U7_LABEL: 0.08}})
        prepared = prepare_strategy_comparison(raw)
        self.assertIn(GM_U7_LABEL, prepared.columns)
        self.assertAlmostEqual(prepared.loc["CAGR", GM_U7_LABEL], 0.08)

    def test_empty_frame_stays_empty(self):
        prepared = prepare_strategy_comparison(pd.DataFrame())
        self.assertTrue(prepared.empty)


if __name__ == "__main__":
    unittest.main()
