# ================================================================
# GLOBAL MOMENTUM BACKTEST
# Universe 7 vs Universe 8 (+ Poland / WIG)
# Base currency: EUR
# ================================================================

import io
import os
import time
from pathlib import Path
from typing import TypedDict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import yfinance as yf


# ------------------------------------------------
# PARAMETERS
# ------------------------------------------------

START = "2006-01-01"
END = None  # None = today

TOP_N = 3
MOMENTUM_PERIODS = [3, 6, 12]
SMA_MONTHS = 10
INITIAL_CAPITAL = 100_000
PLOT_DIR = Path(__file__).with_suffix("")
STOOQ_API_KEY_ENV = "STOOQ_API_KEY"
MIN_WIG_DAILY_ROWS = 260
WIG_CACHE_PATH = PLOT_DIR / "wig_pln.csv"
WIG_CACHE_MAX_AGE_DAYS = 4
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
}

# Existing long-history proxies
ASSETS_7 = {
    "USA": "SPY",
    "Europe": "VGK",
    "Japan": "EWJ",
    "Emerging Markets": "EEM",
    "Bonds": "AGG",
    "Commodities": "DBC",
    "Gold": "GLD",
}

# Safe asset proxy
SAFE_ASSET = "SHY"


class BacktestResult(TypedDict):
    label: str
    returns: pd.Series
    equity: pd.Series
    weights: pd.DataFrame
    ranking: dict[pd.Timestamp, list[str]]


# ------------------------------------------------
# DOWNLOAD YAHOO DATA
# ------------------------------------------------

def download_yahoo(
    tickers: list[str],
    start: str = START,
    end: str | None = END,
) -> pd.DataFrame:
    data = yf.download(
        tickers,
        start=start,
        end=end,
        auto_adjust=True,
        progress=False,
        group_by="column",
    )

    close_data = data["Close"]
    if isinstance(close_data, pd.Series):
        close = close_data.to_frame(tickers[0] if len(tickers) == 1 else "Close")
    else:
        close = close_data.copy()
        if len(tickers) == 1 and len(close.columns) == 1:
            close.columns = tickers

    close.index = pd.to_datetime(close.index)
    return close


# ------------------------------------------------
# DOWNLOAD WIG (Stooq, then Bankier + Biznesradar)
# ------------------------------------------------
# Stooq CSV is the preferred source, but since early 2026 it often returns a
# JavaScript browser-check page unless STOOQ_API_KEY is set. Yahoo's WIG.WA
# series is unusable (a couple of rows). Fall back to Bankier daily history
# plus Biznesradar pages for the recent tail.

def download_wig() -> pd.Series:
    cached = _read_cached_wig()
    if cached is not None and _wig_is_fresh(cached):
        print(
            f"Using cached WIG ({len(cached)} rows, "
            f"{cached.index.min().date()} -> {cached.index.max().date()})."
        )
        return cached

    remote_error: Exception | None = None
    try:
        wig = _download_wig_remote()
    except Exception as exc:
        remote_error = exc
        wig = None

    if wig is not None:
        _write_cached_wig(wig)
        return wig

    if cached is not None:
        print(
            f"Live WIG download failed ({remote_error}); "
            f"using cached series through {cached.index.max().date()}."
        )
        return cached

    raise RuntimeError(
        "Could not download a usable WIG history from Stooq, Bankier, or "
        "Biznesradar. Optionally set STOOQ_API_KEY and rerun."
    ) from remote_error


def _download_wig_remote() -> pd.Series:
    try:
        return _require_enough(_normalize_wig(download_wig_stooq()), "Stooq")
    except (requests.RequestException, ValueError) as stooq_exc:
        print(f"Stooq WIG download failed: {stooq_exc}")

    pieces: list[pd.Series] = []
    sources: list[str] = []

    try:
        bankier = _normalize_wig(download_wig_bankier())
        if not bankier.empty:
            pieces.append(bankier)
            sources.append("Bankier")
            print(
                f"Bankier WIG: {len(bankier)} rows "
                f"({bankier.index.min().date()} -> {bankier.index.max().date()})."
            )
    except (requests.RequestException, ValueError, KeyError) as bankier_exc:
        print(f"Bankier WIG download failed: {bankier_exc}")

    stop_before = pieces[0].index.max() if pieces else None
    try:
        biznesradar = _normalize_wig(
            download_wig_biznesradar(stop_before=stop_before)
        )
        if not biznesradar.empty:
            pieces.append(biznesradar)
            sources.append("Biznesradar")
            print(
                f"Biznesradar WIG: {len(biznesradar)} rows "
                f"({biznesradar.index.min().date()} -> {biznesradar.index.max().date()})."
            )
    except (requests.RequestException, ValueError) as br_exc:
        print(f"Biznesradar WIG download failed: {br_exc}")

    if not pieces:
        raise RuntimeError(
            "Stooq, Bankier, and Biznesradar all failed to return WIG prices."
        )

    wig = pd.concat(pieces)
    wig = wig[~wig.index.duplicated(keep="last")].sort_index()
    return _require_enough(wig, " + ".join(sources))


def _normalize_wig(close: pd.Series) -> pd.Series:
    close = pd.to_numeric(close, errors="coerce").dropna()
    close.index = pd.to_datetime(close.index)
    close = close.sort_index()
    return close.loc[close.index >= START].rename("Poland")


def _require_enough(close: pd.Series, source: str) -> pd.Series:
    if len(close) < MIN_WIG_DAILY_ROWS:
        raise ValueError(
            f"{source} returned only {len(close)} WIG rows; at least "
            f"{MIN_WIG_DAILY_ROWS} daily rows are needed."
        )
    print(
        f"Loaded {len(close)} WIG daily closes from {source} "
        f"({close.index.min().date()} -> {close.index.max().date()})."
    )
    return close


def _wig_is_fresh(wig: pd.Series) -> bool:
    last = pd.Timestamp(wig.index.max()).normalize()
    today = pd.Timestamp.today().normalize()
    return (today - last).days <= WIG_CACHE_MAX_AGE_DAYS


def _read_cached_wig() -> pd.Series | None:
    if not WIG_CACHE_PATH.exists():
        return None
    try:
        df = pd.read_csv(WIG_CACHE_PATH, parse_dates=["Date"], index_col="Date")
        wig = _normalize_wig(df["Close"])
    except (OSError, ValueError, KeyError):
        return None
    if wig.empty:
        return None
    return wig


def _write_cached_wig(wig: pd.Series) -> None:
    PLOT_DIR.mkdir(exist_ok=True)
    wig.rename("Close").to_csv(WIG_CACHE_PATH, index_label="Date")


def download_wig_stooq() -> pd.Series:
    url = "https://stooq.com/q/d/l/?s=wig&i=d"
    api_key = os.environ.get(STOOQ_API_KEY_ENV)
    headers = {**BROWSER_HEADERS, "User-Agent": "Mozilla/5.0"}
    if api_key:
        url = f"{url}&apikey={api_key}"

    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()

    head = r.text[:500].lower()
    if "<html" in head or "javascript" in head:
        raise ValueError(
            "Stooq returned a browser verification page instead of CSV."
        )

    df = pd.read_csv(io.StringIO(r.text))
    df.columns = df.columns.str.strip()

    required_columns = {"Date", "Close"}
    if not required_columns.issubset(df.columns):
        preview = r.text[:300].replace("\n", " ")
        raise ValueError(
            "Stooq response is not the expected Date/Open/High/Low/Close CSV. "
            f"Columns: {list(df.columns)}. Response preview: {preview!r}"
        )

    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").sort_index()
    return df["Close"].rename("Poland")


def download_wig_bankier() -> pd.Series:
    session = requests.Session()
    session.headers.update(
        {
            **BROWSER_HEADERS,
            "Accept": "application/json,text/plain,*/*",
            "Referer": (
                "https://www.bankier.pl/inwestowanie/profile/quote.html"
                "?symbol=WIG"
            ),
        }
    )

    frames: list[pd.Series] = []
    start_year = pd.Timestamp(START).year
    this_year = pd.Timestamp.today().year
    year = start_year
    while year <= this_year:
        chunk_end_year = min(year + 4, this_year)
        date_from = int(
            pd.Timestamp(year=year, month=1, day=1, tz="UTC").timestamp() * 1000
        )
        date_to = int(
            pd.Timestamp(
                year=chunk_end_year, month=12, day=31, tz="UTC"
            ).timestamp()
            * 1000
        )
        url = (
            "https://www.bankier.pl/new-charts/get-data"
            f"?symbol=WIG&date_from={date_from}&date_to={date_to}"
            "&intraday=false&type=area"
        )
        r = session.get(url, timeout=30)
        r.raise_for_status()
        main = r.json().get("main") or []
        if main:
            chunk = pd.DataFrame(main, columns=["ts", "Close"])
            chunk["Date"] = pd.to_datetime(
                chunk["ts"], unit="ms", utc=True
            ).dt.tz_convert(None)
            frames.append(chunk.set_index("Date")["Close"])
        year = chunk_end_year + 1

    if not frames:
        raise ValueError("Bankier chart API returned no WIG points.")

    wig = pd.concat(frames)
    wig = wig[~wig.index.duplicated(keep="last")].sort_index()
    return wig.rename("Poland")


def download_wig_biznesradar(
    stop_before: pd.Timestamp | None = None,
) -> pd.Series:
    session = requests.Session()
    session.headers.update(BROWSER_HEADERS)
    cutoff = (
        pd.Timestamp(stop_before)
        if stop_before is not None
        else pd.Timestamp(START)
    )
    base_url = "https://www.biznesradar.pl/notowania-historyczne/WIG"
    frames: list[pd.Series] = []

    for page in range(1, 201):
        url = base_url if page == 1 else f"{base_url},{page}"
        r = session.get(url, timeout=30)
        r.raise_for_status()
        tables = pd.read_html(
            io.StringIO(r.text),
            attrs={"class": "qTableFull"},
            flavor="lxml",
        )
        if not tables or tables[0].empty:
            break

        raw = tables[0]
        chunk = pd.DataFrame(
            {
                "Date": pd.to_datetime(raw.iloc[:, 0], dayfirst=True),
                "Close": pd.to_numeric(raw.iloc[:, 4], errors="coerce"),
            }
        ).dropna()
        close = chunk.set_index("Date")["Close"]
        if close.empty:
            break
        frames.append(close)
        if close.index.min() <= cutoff:
            break
        time.sleep(0.15)

    if not frames:
        raise ValueError("Biznesradar returned no WIG rows.")

    wig = pd.concat(frames)
    wig = wig[~wig.index.duplicated(keep="last")].sort_index()
    return wig.rename("Poland")


def load_monthly_prices() -> pd.DataFrame:
    # ------------------------------------------------
    # DOWNLOAD DATA
    # ------------------------------------------------

    tickers = list(ASSETS_7.values()) + [SAFE_ASSET]
    prices_usd = download_yahoo(tickers)
    wig_pln = download_wig()

    # FX rates
    # EURUSD = USD per EUR
    # EURPLN = PLN per EUR
    fx = download_yahoo(["EURUSD=X", "EURPLN=X"])
    fx.columns = ["EURUSD", "EURPLN"]

    # ------------------------------------------------
    # CONVERT EVERYTHING TO EUR
    # ------------------------------------------------

    # synchronize daily indices
    all_daily = prices_usd.join(fx, how="inner")
    prices_eur = pd.DataFrame(index=all_daily.index)

    # USD assets -> EUR
    for name, ticker in ASSETS_7.items():
        prices_eur[name] = all_daily[ticker] / all_daily["EURUSD"]

    # safe asset
    prices_eur["Safe"] = all_daily[SAFE_ASSET] / all_daily["EURUSD"]

    # WIG PLN -> EUR
    wig = wig_pln.to_frame()
    wig = wig.join(fx["EURPLN"], how="inner")
    wig["Poland"] = wig["Poland"] / wig["EURPLN"]
    prices_eur = prices_eur.join(wig["Poland"], how="outer")

    # ------------------------------------------------
    # MONTH-END DATA
    # ------------------------------------------------

    monthly = prices_eur.resample("ME").last()
    return monthly.dropna(subset=list(ASSETS_7.keys()) + ["Safe"])


# ------------------------------------------------
# MOMENTUM CALCULATION
# ------------------------------------------------

def momentum_score(prices: pd.DataFrame) -> pd.DataFrame:
    scores = []
    for months in MOMENTUM_PERIODS:
        r = prices / prices.shift(months) - 1
        scores.append(r)

    return sum(scores) / len(scores)


# ------------------------------------------------
# BACKTEST FUNCTION
# ------------------------------------------------

def backtest(
    monthly: pd.DataFrame,
    asset_names: list[str],
    label: str,
) -> BacktestResult:
    prices = monthly[asset_names]
    safe = monthly["Safe"]
    momentum = momentum_score(prices)
    sma = prices.rolling(SMA_MONTHS).mean()
    monthly_returns = prices.pct_change()
    safe_returns = safe.pct_change()

    portfolio_returns = pd.Series(index=monthly.index, dtype=float)
    weights_history = pd.DataFrame(
        0.0,
        index=monthly.index,
        columns=asset_names + ["Safe"],
    )
    ranking_history = {}
    first_valid = max(max(MOMENTUM_PERIODS), SMA_MONTHS)

    for i in range(first_valid, len(monthly) - 1):
        signal_date = monthly.index[i]
        investment_date = monthly.index[i + 1]
        scores = momentum.iloc[i].dropna()
        ranking = scores.sort_values(ascending=False)
        top = ranking.head(TOP_N).index

        ranking_history[signal_date] = list(top)
        weight = 1 / TOP_N
        portfolio_return = 0.0
        safe_weight = 0.0

        for asset in top:
            # Trend filter
            if prices.loc[signal_date, asset] > sma.loc[signal_date, asset]:
                portfolio_return += (
                    weight * monthly_returns.loc[investment_date, asset]
                )
                weights_history.loc[investment_date, asset] = weight
            else:
                safe_weight += weight

        # capital failing SMA goes to safe asset
        if safe_weight > 0:
            portfolio_return += safe_weight * safe_returns.loc[investment_date]
            weights_history.loc[investment_date, "Safe"] = safe_weight

        portfolio_returns.loc[investment_date] = portfolio_return

    portfolio_returns = portfolio_returns.dropna()
    weights_history = weights_history.loc[portfolio_returns.index]
    equity = INITIAL_CAPITAL * (1 + portfolio_returns).cumprod()

    return {
        "label": label,
        "returns": portfolio_returns,
        "equity": equity,
        "weights": weights_history,
        "ranking": ranking_history,
    }


# ------------------------------------------------
# METRICS
# ------------------------------------------------

def metrics(result: BacktestResult) -> dict[str, float]:
    r = result["returns"]
    equity = result["equity"]
    years = len(r) / 12

    total_return = equity.iloc[-1] / INITIAL_CAPITAL - 1
    cagr = (equity.iloc[-1] / INITIAL_CAPITAL) ** (1 / years) - 1
    volatility = r.std() * np.sqrt(12)
    running_max = equity.cummax()
    drawdown = equity / running_max - 1
    max_dd = drawdown.min()
    annual_returns = (1 + r).groupby(r.index.year).prod() - 1
    worst_year = annual_returns.min()

    # turnover
    weights = result["weights"]
    turnover_monthly = weights.diff().abs().sum(axis=1) / 2
    turnover_annual = turnover_monthly.mean() * 12

    return {
        "Total Return": total_return,
        "CAGR": cagr,
        "Volatility": volatility,
        "Max Drawdown": max_dd,
        "Worst Year": worst_year,
        "Annual Turnover": turnover_annual,
        "End Value": equity.iloc[-1],
    }


def annual_returns(result: BacktestResult) -> pd.Series:
    r = result["returns"]
    return (1 + r).groupby(r.index.year).prod() - 1


def drawdown(equity: pd.Series) -> pd.Series:
    return equity / equity.cummax() - 1


def save_plot(filename: str) -> None:
    PLOT_DIR.mkdir(exist_ok=True)
    output_path = PLOT_DIR / filename
    plt.savefig(output_path, dpi=150)
    print(f"Saved plot: {output_path}")
    plt.close()


# ------------------------------------------------
# RUN BACKTESTS
# ------------------------------------------------

def main() -> None:
    monthly = load_monthly_prices()
    universe7 = list(ASSETS_7.keys())
    universe8 = universe7 + ["Poland"]

    bt7 = backtest(monthly, universe7, "TOP3 - Universe 7")
    bt8 = backtest(monthly, universe8, "TOP3 - Universe 8 + Poland")

    # ------------------------------------------------
    # RESULTS TABLE
    # ------------------------------------------------

    m7 = metrics(bt7)
    m8 = metrics(bt8)
    comparison = pd.DataFrame(
        {
            "Universe 7": m7,
            "Universe 8 + Poland": m8,
        }
    )

    print("\n")
    print("=" * 70)
    print("GLOBAL MOMENTUM BACKTEST")
    print("=" * 70)
    print(comparison)
    print("\n")

    # percentage display
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

    # ------------------------------------------------
    # POLAND ANALYSIS
    # ------------------------------------------------

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
    print(f"Poland in TOP3: {number_poland} months")
    print(f"All signals: {total_signals}")
    print(f"Frequency: {frequency:.1%}")

    # ------------------------------------------------
    # WHICH ASSET POLAND REPLACES
    # ------------------------------------------------

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

    print("\nAssets most often displaced by Poland:")
    for asset, count in sorted(
        replacement_counts.items(),
        key=lambda x: x[1],
        reverse=True,
    ):
        print(f"{asset:20s}: {count}")

    # ------------------------------------------------
    # ANNUAL RETURNS
    # ------------------------------------------------

    annual = pd.DataFrame(
        {
            "Universe 7": annual_returns(bt7),
            "Universe 8 + Poland": annual_returns(bt8),
        }
    )

    print("\n")
    print("=" * 70)
    print("ANNUAL RETURNS")
    print("=" * 70)
    print(annual.map(lambda x: f"{x:.2%}"))

    # ------------------------------------------------
    # DIFFERENCE CAUSED BY POLAND
    # ------------------------------------------------

    annual["Difference"] = annual["Universe 8 + Poland"] - annual["Universe 7"]

    print("\nBest years for adding Poland:")
    print(annual.sort_values("Difference", ascending=False).head())

    print("\nWorst years for adding Poland:")
    print(annual.sort_values("Difference").head())

    # ------------------------------------------------
    # EQUITY CURVE
    # ------------------------------------------------

    plt.figure(figsize=(12, 6))
    plt.plot(bt7["equity"], label="Universe 7")
    plt.plot(bt8["equity"], label="Universe 8 + Poland")
    plt.title(
        "Global Momentum TOP3 - "
        "Universe 7 vs Universe 8 + Poland"
    )
    plt.ylabel("Portfolio value (EUR)")
    plt.xlabel("Date")
    plt.grid(alpha=0.3)
    plt.legend()
    plt.tight_layout()
    save_plot("equity_curve.png")

    # ------------------------------------------------
    # DRAWDOWN CHART
    # ------------------------------------------------

    plt.figure(figsize=(12, 5))
    plt.plot(drawdown(bt7["equity"]), label="Universe 7")
    plt.plot(drawdown(bt8["equity"]), label="Universe 8 + Poland")
    plt.title("Drawdown - Universe 7 vs Poland")
    plt.ylabel("Drawdown")
    plt.xlabel("Date")
    plt.grid(alpha=0.3)
    plt.legend()
    plt.tight_layout()
    save_plot("drawdown.png")


if __name__ == "__main__":
    main()
