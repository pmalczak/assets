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
    annual_returns,
    backtest,
    build_benchmarks,
    diagnose_monthly_returns,
    display_name,
    download_polish_cpi,
    drawdown,
    load_monthly_prices,
    metrics,
    print_strategy_comparison,
    save_plot,
)


# ------------------------------------------------
# RUN BACKTESTS
# ------------------------------------------------

def main() -> None:
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
            "GM U8": bt8,
            **benchmarks,
            "GM U7 (diagnostic)": bt7,
        },
        polish_cpi,
    )

    poland_top3 = []
    for date, ranking in bt8["ranking"].items():
        if "Poland" in ranking:
            poland_top3.append(date)

    number_poland = len(poland_top3)
    total_signals = len(bt8["ranking"])
    frequency = number_poland / total_signals if total_signals > 0 else 0

    print("\n")
    print("=" * 70)
    print("POLAND / WIG ANALYSIS")
    print("=" * 70)
    print(f"{display_name('Poland')} in TOP3: {number_poland} months")
    print(f"All signals: {total_signals}")
    print(f"Frequency: {frequency:.1%}")

    replacement_counts = {}
    for date in bt8["ranking"]:
        r8 = bt8["ranking"][date]
        if "Poland" not in r8:
            continue
        if date not in bt7["ranking"]:
            continue

        r7 = bt7["ranking"][date]
        removed = set(r7) - set(r8)
        for asset in removed:
            replacement_counts[asset] = replacement_counts.get(asset, 0) + 1

    print(f"\nAssets most often displaced by {display_name('Poland')}:")
    replacement_width = max(
        32,
        *(len(display_name(asset)) for asset in replacement_counts),
    )
    for asset, count in sorted(
        replacement_counts.items(),
        key=lambda x: x[1],
        reverse=True,
    ):
        print(f"{display_name(asset):{replacement_width}s}: {count}")

    annual = pd.DataFrame(
        {
            "Universe 7": annual_returns(bt7),
            universe8_label: annual_returns(bt8),
        }
    )

    print("\n")
    print("=" * 70)
    print("ANNUAL RETURNS")
    print("=" * 70)
    print(annual.map(lambda x: f"{x:.2%}"))

    annual["Difference"] = annual[universe8_label] - annual["Universe 7"]

    print(f"\nBest years for adding {display_name('Poland')}:")
    print(annual.sort_values("Difference", ascending=False).head())

    print(f"\nWorst years for adding {display_name('Poland')}:")
    print(annual.sort_values("Difference").head())

    plt.figure(figsize=(12, 6))
    plt.plot(bt8["equity"], label="Global Momentum U8")
    plt.plot(benchmarks["All-World Buy & Hold"]["equity"], label="All-World Buy & Hold")
    plt.plot(benchmarks["60/40"]["equity"], label="60/40")
    plt.plot(bt7["equity"], label="GM U7 diagnostic", linestyle="--", alpha=0.7)
    plt.title("Global Momentum U8 vs All-World and 60/40")
    plt.ylabel("Portfolio value (EUR)")
    plt.xlabel("Date")
    plt.grid(alpha=0.3)
    plt.legend()
    plt.tight_layout()
    save_plot("equity_curve.png")

    plt.figure(figsize=(12, 5))
    plt.plot(drawdown(bt8["equity"]), label="Global Momentum U8")
    plt.plot(drawdown(benchmarks["All-World Buy & Hold"]["equity"]), label="All-World Buy & Hold")
    plt.plot(drawdown(benchmarks["60/40"]["equity"]), label="60/40")
    plt.plot(drawdown(bt7["equity"]), label="GM U7 diagnostic", linestyle="--", alpha=0.7)
    plt.title("Drawdown - Global Momentum U8 vs All-World and 60/40")
    plt.ylabel("Drawdown")
    plt.xlabel("Date")
    plt.grid(alpha=0.3)
    plt.legend()
    plt.tight_layout()
    save_plot("drawdown.png")


if __name__ == "__main__":
    main()
