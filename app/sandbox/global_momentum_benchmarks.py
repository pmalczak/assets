# ================================================================
# GLOBAL MOMENTUM BENCHMARKS
# Historical research and validation for Global Momentum U8
# ================================================================

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from global_momentum_common import (
    ASSETS_7,
    align_result_to_index,
    annual_returns,
    backtest,
    build_benchmarks,
    diagnose_monthly_returns,
    display_name,
    download_polish_cpi,
    drawdown,
    extended_metrics,
    load_monthly_prices,
    metrics,
    print_strategy_comparison,
    save_plot,
)


# ------------------------------------------------
# RUN BACKTESTS
# ------------------------------------------------

def run_benchmarks() -> dict:
    monthly = load_monthly_prices()
    universe7 = list(ASSETS_7.keys())
    universe8 = universe7 + ["Poland"]
    universe8_label = f"Universe 8 + {display_name('Poland')}"

    diagnose_monthly_returns(monthly[universe8 + ["Safe"]], "strategy prices")

    bt7 = backtest(monthly, universe7, "TOP3 - Universe 7")
    bt8 = backtest(monthly, universe8, f"TOP3 - {universe8_label}")
    benchmarks = build_benchmarks(monthly)
    polish_cpi = download_polish_cpi()

    m7 = metrics(bt7)
    m8 = metrics(bt8)
    comparison = pd.DataFrame(
        {
            "Universe 7": m7,
            universe8_label: m8,
        }
    )

    strategy_results = {
        "GM U8": bt8,
        **benchmarks,
        "GM U7 (diagnostic)": bt7,
    }
    strategy_comparison, comparison_period = strategy_comparison_table(
        strategy_results,
        polish_cpi,
    )

    poland_top3 = [
        date for date, ranking in bt8["ranking"].items() if "Poland" in ranking
    ]
    number_poland = len(poland_top3)
    total_signals = len(bt8["ranking"])
    frequency = number_poland / total_signals if total_signals > 0 else 0.0

    replacement_counts: dict[str, int] = {}
    for date in bt8["ranking"]:
        r8 = bt8["ranking"][date]
        if "Poland" not in r8 or date not in bt7["ranking"]:
            continue
        for asset in set(bt7["ranking"][date]) - set(r8):
            replacement_counts[asset] = replacement_counts.get(asset, 0) + 1

    displaced = pd.DataFrame(
        [
            {"Asset": display_name(asset), "Months": count}
            for asset, count in sorted(
                replacement_counts.items(),
                key=lambda item: item[1],
                reverse=True,
            )
        ]
    )

    annual = pd.DataFrame(
        {
            "Universe 7": annual_returns(bt7),
            universe8_label: annual_returns(bt8),
        }
    )
    annual["Difference"] = annual[universe8_label] - annual["Universe 7"]

    equity = pd.DataFrame(
        {
            "Global Momentum U8": bt8["equity"],
            "All-World Buy & Hold": benchmarks["All-World Buy & Hold"]["equity"],
            "60/40": benchmarks["60/40"]["equity"],
            "GM U7 diagnostic": bt7["equity"],
        }
    )
    drawdowns = pd.DataFrame(
        {
            "Global Momentum U8": drawdown(bt8["equity"]),
            "All-World Buy & Hold": drawdown(
                benchmarks["All-World Buy & Hold"]["equity"]
            ),
            "60/40": drawdown(benchmarks["60/40"]["equity"]),
            "GM U7 diagnostic": drawdown(bt7["equity"]),
        }
    )

    return {
        "universe8_label": universe8_label,
        "comparison": comparison,
        "strategy_comparison": strategy_comparison,
        "comparison_period": comparison_period,
        "cpi_through": polish_cpi.index.max().date() if not polish_cpi.empty else None,
        "poland_in_top3": number_poland,
        "total_signals": total_signals,
        "poland_frequency": frequency,
        "displaced": displaced,
        "annual": annual,
        "equity": equity,
        "drawdown": drawdowns,
        "bt7": bt7,
        "bt8": bt8,
        "benchmarks": benchmarks,
        "polish_cpi": polish_cpi,
    }


def strategy_comparison_table(
    results: dict,
    cpi: pd.Series,
) -> tuple[pd.DataFrame, tuple | None]:
    common_index = None
    for result in results.values():
        idx = result["returns"].dropna().index
        common_index = idx if common_index is None else common_index.intersection(idx)

    if common_index is None or common_index.empty:
        return pd.DataFrame(), None

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
    return comparison, (common_index.min().date(), common_index.max().date())


def main() -> None:
    result = run_benchmarks()
    universe8_label = result["universe8_label"]
    comparison = result["comparison"]
    m7 = comparison["Universe 7"]
    m8 = comparison[universe8_label]

    print("\n")
    print("=" * 70)
    print("GLOBAL MOMENTUM BACKTEST")
    print("Primary strategy: Global Momentum U8")
    print("=" * 70)
    print(comparison)
    print("\n")

    for metric in [
        "Total Return",
        "CAGR",
        "Volatility",
        "Max Drawdown",
        "Worst Year",
        "Annual Turnover",
    ]:
        print(
            f"{metric:20s}",
            f"U7: {m7[metric]:8.2%}",
            f"U8: {m8[metric]:8.2%}",
        )

    print_strategy_comparison(
        {
            "GM U8": result["bt8"],
            **result["benchmarks"],
            "GM U7 (diagnostic)": result["bt7"],
        },
        result["polish_cpi"],
    )

    print("\n")
    print("=" * 70)
    print("POLAND / WIG ANALYSIS")
    print("=" * 70)
    print(f"{display_name('Poland')} in TOP3: {result['poland_in_top3']} months")
    print(f"All signals: {result['total_signals']}")
    print(f"Frequency: {result['poland_frequency']:.1%}")

    displaced = result["displaced"]
    print(f"\nAssets most often displaced by {display_name('Poland')}:")
    if displaced.empty:
        print("(none)")
    else:
        replacement_width = max(32, *(len(str(name)) for name in displaced["Asset"]))
        for row in displaced.to_dict("records"):
            print(f"{row['Asset']:{replacement_width}s}: {row['Months']}")

    annual = result["annual"]
    print("\n")
    print("=" * 70)
    print("ANNUAL RETURNS")
    print("=" * 70)
    print(annual.drop(columns=["Difference"]).map(lambda x: f"{x:.2%}"))

    print(f"\nBest years for adding {display_name('Poland')}:")
    print(annual.sort_values("Difference", ascending=False).head())

    print(f"\nWorst years for adding {display_name('Poland')}:")
    print(annual.sort_values("Difference").head())

    plt.figure(figsize=(12, 6))
    for column in result["equity"].columns:
        style = "--" if column == "GM U7 diagnostic" else "-"
        alpha = 0.7 if column == "GM U7 diagnostic" else 1.0
        plt.plot(result["equity"][column], label=column, linestyle=style, alpha=alpha)
    plt.title("Global Momentum U8 vs All-World and 60/40")
    plt.ylabel("Portfolio value (EUR)")
    plt.xlabel("Date")
    plt.grid(alpha=0.3)
    plt.legend()
    plt.tight_layout()
    save_plot("equity_curve.png")

    plt.figure(figsize=(12, 5))
    for column in result["drawdown"].columns:
        style = "--" if column == "GM U7 diagnostic" else "-"
        alpha = 0.7 if column == "GM U7 diagnostic" else 1.0
        plt.plot(result["drawdown"][column], label=column, linestyle=style, alpha=alpha)
    plt.title("Drawdown - Global Momentum U8 vs All-World and 60/40")
    plt.ylabel("Drawdown")
    plt.xlabel("Date")
    plt.grid(alpha=0.3)
    plt.legend()
    plt.tight_layout()
    save_plot("drawdown.png")


if __name__ == "__main__":
    main()
