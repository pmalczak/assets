# ================================================================
# GLOBAL MOMENTUM BENCHMARKS
# Historical research and validation for Global Momentum U7
# ================================================================

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from global_momentum.global_momentum_common import (
    align_result_to_index,
    annual_returns,
    backtest,
    benchmark_result,
    build_benchmarks,
    diagnose_monthly_returns,
    download_polish_cpi,
    drawdown,
    extended_metrics,
    format_metric_table,
    load_monthly_prices,
    metrics,
    save_plot,
    weighted_monthly_returns, BacktestResult,
)


U7 = [
    "USA",
    "Europe",
    "Japan",
    "Emerging Markets",
    "Bonds",
    "Commodities",
    "Poland",
]
GM_U7_LABEL = "GM U7"
U7_EQUAL_WEIGHT_LABEL = "U7 Equal Weight"
EXPECTED_U7_METRICS = {
    "CAGR": 0.0813,
    "Volatility": 0.1269,
    "Max Drawdown": -0.2558,
}
EXPECTED_U7_TOLERANCE = {
    "CAGR": 0.003,
    "Volatility": 0.005,
    "Max Drawdown": 0.01,
}
# ------------------------------------------------
# RUN BACKTESTS
# ------------------------------------------------

def run_benchmarks() -> dict:
    monthly = load_monthly_prices()

    diagnose_monthly_returns(monthly[U7 + ["Safe"]], "strategy prices")

    bt7 = backtest(monthly, U7, f"TOP3 - {GM_U7_LABEL}")
    benchmarks = {
        label: result
        for label, result in build_benchmarks(monthly).items()
        if label != "60/40"
    }
    polish_cpi = download_polish_cpi()

    baseline_comparison, _, _ = strategy_comparison_table(
        {
            GM_U7_LABEL: bt7,
            **benchmarks,
        },
        polish_cpi,
    )
    assert_expected_u7_metrics(baseline_comparison[GM_U7_LABEL].to_dict())

    u7_equal_weight = build_u7_equal_weight_benchmark(monthly)
    strategy_results = {
        GM_U7_LABEL: bt7,
        U7_EQUAL_WEIGHT_LABEL: u7_equal_weight,
        **benchmarks,
    }
    strategy_comparison, comparison_period, common_results = strategy_comparison_table(
        strategy_results,
        polish_cpi,
    )
    if GM_U7_LABEL not in strategy_comparison.columns:
        raise ValueError(
            "Strategy comparison is missing GM U7 "
            f"(columns={list(strategy_comparison.columns)})."
        )
    comparison = pd.DataFrame(
        {
            GM_U7_LABEL: metrics(bt7),
        }
    )

    annual = pd.DataFrame(
        {
            GM_U7_LABEL: annual_returns(common_results[GM_U7_LABEL]),
            U7_EQUAL_WEIGHT_LABEL: annual_returns(
                common_results[U7_EQUAL_WEIGHT_LABEL]
            ),
        }
    )

    equity = pd.DataFrame(
        {
            GM_U7_LABEL: common_results[GM_U7_LABEL]["equity"],
            U7_EQUAL_WEIGHT_LABEL: common_results[U7_EQUAL_WEIGHT_LABEL]["equity"],
            "All-World": common_results["All-World Buy & Hold"]["equity"],
        }
    )
    drawdowns = pd.DataFrame(
        {
            GM_U7_LABEL: drawdown(common_results[GM_U7_LABEL]["equity"]),
            U7_EQUAL_WEIGHT_LABEL: drawdown(
                common_results[U7_EQUAL_WEIGHT_LABEL]["equity"]
            ),
            "All-World": drawdown(common_results["All-World Buy & Hold"]["equity"]),
        }
    )

    return {
        "universe7_label": GM_U7_LABEL,
        "universe8_label": GM_U7_LABEL,
        "comparison": comparison,
        "strategy_comparison": strategy_comparison,
        "comparison_period": comparison_period,
        "cpi_through": polish_cpi.index.max().date() if not polish_cpi.empty else None,
        "annual": annual,
        "equity": equity,
        "drawdown": drawdowns,
        "bt7": bt7,
        "bt8": bt7,
        "u7_equal_weight": u7_equal_weight,
        "benchmarks": benchmarks,
        "polish_cpi": polish_cpi,
    }


def strategy_comparison_table(
    results: dict,
    cpi: pd.Series,
) -> tuple[pd.DataFrame, tuple | None, dict]:
    common_index = None
    for result in results.values():
        idx = result["returns"].dropna().index
        common_index = idx if common_index is None else common_index.intersection(idx)

    if common_index is None or common_index.empty:
        return pd.DataFrame(), None, {}

    common_results = {
        label: align_result_to_index(result, common_index)
        for label, result in results.items()
    }
    comparison = pd.DataFrame(
        {
            label: extended_metrics(result, cpi)
            for label, result in common_results.items()
        }
    )
    return comparison, (common_index.min().date(), common_index.max().date()), common_results


def prepare_strategy_comparison(strategy: pd.DataFrame | None) -> pd.DataFrame:
    if strategy is None or strategy.empty:
        return pd.DataFrame()
    out = strategy.copy()
    out.columns = [str(column).strip() for column in out.columns]
    out.index = [str(index).strip() for index in out.index]
    if GM_U7_LABEL not in out.columns and GM_U7_LABEL in out.index and "CAGR" in out.columns:
        out = out.T
        out.columns = [str(column).strip() for column in out.columns]
    return out


def build_u7_equal_weight_benchmark(monthly: pd.DataFrame) -> BacktestResult:
    weights = {asset: 1 / len(U7) for asset in U7}
    returns = weighted_monthly_returns(monthly, weights).rename(U7_EQUAL_WEIGHT_LABEL)
    weights_frame = pd.DataFrame(
        weights,
        index=returns.dropna().index,
    )
    result = benchmark_result(
        returns,
        U7_EQUAL_WEIGHT_LABEL,
        weights_frame,
    )
    return result


def assert_expected_u7_metrics(u7_metrics: dict[str, float]) -> None:
    gm_u7_cagr = u7_metrics["CAGR"]
    gm_u7_vol = u7_metrics["Volatility"]
    gm_u7_max_dd = u7_metrics["Max Drawdown"]
    assert abs(gm_u7_cagr - 0.0813) < 0.003, (
        f"GM U7 CAGR validation failed: {gm_u7_cagr:.4%}"
    )
    assert abs(gm_u7_vol - 0.1269) < 0.005, (
        f"GM U7 volatility validation failed: {gm_u7_vol:.4%}"
    )
    assert abs(gm_u7_max_dd - (-0.2558)) < 0.01, (
        f"GM U7 max drawdown validation failed: {gm_u7_max_dd:.4%}"
    )


def format_percent_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.map(lambda x: "" if pd.isna(x) else f"{x:.2%}")


def main() -> None:
    result = run_benchmarks()

    print("\n")
    print("=" * 70)
    print("GLOBAL MOMENTUM BACKTEST")
    print("Primary strategy: Global Momentum U7")
    print("=" * 70)
    start, end = result["comparison_period"]
    print(f"Common nominal period: {start} -> {end}")
    print(f"Polish CPI available through: {result['cpi_through']}")
    print(format_metric_table(result["strategy_comparison"]).to_string())

    print("\n")
    print("=" * 70)
    print("U7 PORTFOLIO BENCHMARK")
    print("=" * 70)
    top_n_columns = [
        GM_U7_LABEL,
        U7_EQUAL_WEIGHT_LABEL,
    ]
    print(
        format_metric_table(result["strategy_comparison"][top_n_columns]).to_string()
    )

    annual = result["annual"]
    print("\n")
    print("=" * 70)
    print("ANNUAL RETURNS")
    print("=" * 70)
    print(format_percent_frame(annual).to_string())

    plt.figure(figsize=(12, 6))
    for column in result["equity"].columns:
        plt.plot(result["equity"][column], label=column)
    plt.title("Global Momentum U7, U7 Equal Weight, and All-World")
    plt.ylabel("Portfolio value (EUR)")
    plt.xlabel("Date")
    plt.grid(alpha=0.3)
    plt.legend()
    plt.tight_layout()
    save_plot("equity_curve.png")

    plt.figure(figsize=(12, 5))
    for column in result["drawdown"].columns:
        plt.plot(result["drawdown"][column], label=column)
    plt.title("Drawdown - Global Momentum U7, U7 Equal Weight, and All-World")
    plt.ylabel("Drawdown")
    plt.xlabel("Date")
    plt.grid(alpha=0.3)
    plt.legend()
    plt.tight_layout()
    save_plot("drawdown.png")


if __name__ == "__main__":
    main()
