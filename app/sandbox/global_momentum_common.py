# ================================================================
# GLOBAL MOMENTUM BACKTEST
# Universe 7 vs Universe 8 (+ Poland / WIG)
# Base currency: EUR
# ================================================================

import io
import os
import time
from pathlib import Path
from typing import NotRequired, TypedDict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests

from data_step.data_step import DATA_STEP
from yahoo_finance.repository import download_yahoo as _download_yahoo


# ------------------------------------------------
# PARAMETERS
# ------------------------------------------------

START = "2006-01-01"
END = None  # None = today

TOP_N = 3
MOMENTUM_PERIODS = [3, 6, 12]
SMA_MONTHS = 10
INITIAL_CAPITAL = 100_000
MONTHLY_RETURN_WARNING_THRESHOLD = 0.40
MONTHLY_RETURN_ASSERTION_THRESHOLD = 0.80
MONTHLY_RETURN_ASSERTION_WHITELIST: set[str] = set()
PLOT_DIR = Path(__file__).with_name("global_momentum_wig_backtest")
STOOQ_API_KEY_ENV = "STOOQ_API_KEY"
MIN_WIG_DAILY_ROWS = 260
WIG_CACHE_PATH = PLOT_DIR / "wig_pln.csv"
WIG_CACHE_MAX_AGE_DAYS = 4
GLOBAL_EQUITY_BENCHMARK = "ACWI"
BOND_EUR_HEDGED_BENCHMARK = "EUNH.DE"
GLOBAL_EQUITY_BACKFILL_WEIGHTS = {
    "USA": 0.55,
    "Europe": 0.25,
    "Japan": 0.10,
    "Emerging Markets": 0.10,
}
BOND_BACKFILL_ASSET = "Bonds"
POLISH_CPI_FRED_SERIES = "POLCPIALLMINMEI"
CPI_CACHE_PATH = PLOT_DIR / "polish_cpi.csv"
CPI_FRED_CHUNK_MONTHS = 3
CPI_CACHE_MAX_AGE_MONTHS = 18
WORLD_BANK_POLISH_CPI_URL = (
    "https://api.worldbank.org/v2/country/POL/indicator/FP.CPI.TOTL"
    "?format=json&per_page=20000"
)
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
SAFE_ASSET = "XEON.DE"
SAFE_BACKFILL_ASSET = "SHY"

# Execution tickers shown in reports; some backtest series use historical proxies.
DISPLAY_NAMES = {
    "USA": "USA [SXR8.DE]",
    "Europe": "Europe [EUNK.DE]",
    "Japan": "Japan [EUNN.DE]",
    "Emerging Markets": "Emerging Markets [IS3N.DE]",
    "Bonds": "Bonds [EUNA.DE]",
    "Commodities": "Commodities [SXRS.DE]",
    "Gold": "Gold [PPFB.DE]",
    "Poland": "Poland [ETFPZUW20M40.PL]",
    "Safe": "Safe [EXVM / ETFBCASH.PL]",
}


class BacktestResult(TypedDict):
    label: str
    returns: pd.Series
    equity: pd.Series
    weights: pd.DataFrame
    ranking: dict[pd.Timestamp, list[str]]
    turnover: NotRequired[pd.Series]


def display_name(asset: str) -> str:
    return DISPLAY_NAMES.get(asset, asset)


# ------------------------------------------------
# DOWNLOAD YAHOO DATA
# ------------------------------------------------

def download_yahoo(
    tickers: list[str],
    start: str = START,
    end: str | None = END,
) -> pd.DataFrame:
    DATA_STEP.init_steps(root=Path(__file__).resolve().parent.parent)
    return _download_yahoo(tickers, start=start, end=end)


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


def chain_link_prices(
    old_proxy: pd.Series,
    new_instrument: pd.Series,
    label: str,
) -> pd.Series:
    old_proxy = pd.to_numeric(old_proxy, errors="coerce").dropna().sort_index()
    new_instrument = pd.to_numeric(
        new_instrument,
        errors="coerce",
    ).dropna().sort_index()

    common_dates = old_proxy.index.intersection(new_instrument.index)
    valid_common_dates = [
        date
        for date in common_dates
        if old_proxy.loc[date] > 0 and new_instrument.loc[date] > 0
    ]
    if not valid_common_dates:
        raise ValueError(f"No valid overlap date for chain-linking {label}.")

    splice_date = min(valid_common_dates)
    scale = new_instrument.loc[splice_date] / old_proxy.loc[splice_date]
    scaled_old = old_proxy * scale
    linked = pd.concat(
        [
            scaled_old.loc[scaled_old.index < splice_date],
            new_instrument.loc[new_instrument.index >= splice_date],
        ]
    )
    linked = linked[~linked.index.duplicated(keep="last")].sort_index()

    print(
        f"Splice {display_name(label)}: date={splice_date.date()}, "
        f"scale={scale:.8f}, old={old_proxy.loc[splice_date]:.4f}, "
        f"new={new_instrument.loc[splice_date]:.4f}"
    )
    return linked.rename(label)


def diagnose_monthly_returns(
    prices: pd.DataFrame,
    label: str,
) -> None:
    returns = prices.pct_change()
    large_returns = (
        returns[returns.abs() > MONTHLY_RETURN_WARNING_THRESHOLD]
        .stack()
        .dropna()
    )

    if not large_returns.empty:
        print("\n")
        print("=" * 70)
        print(f"MONTHLY RETURN DIAGNOSTICS - {label}")
        print("=" * 70)
        for (date, asset), value in large_returns.items():
            previous_price = prices[asset].shift(1).loc[date]
            current_price = prices[asset].loc[date]
            shown_asset = display_name(asset)
            print(
                f"{shown_asset:<32} {date.date()} "
                f"prev={previous_price:>12.4f} "
                f"curr={current_price:>12.4f} "
                f"return={value:>9.2%}"
            )

    assertion_returns = returns.drop(
        columns=list(MONTHLY_RETURN_ASSERTION_WHITELIST),
        errors="ignore",
    )
    failures = assertion_returns[
        assertion_returns.abs() > MONTHLY_RETURN_ASSERTION_THRESHOLD
    ].stack().dropna()
    if not failures.empty:
        details = []
        for (date, asset), value in failures.items():
            previous_price = prices[asset].shift(1).loc[date]
            current_price = prices[asset].loc[date]
            details.append(
                f"{display_name(asset)} {date.date()} prev={previous_price:.4f} "
                f"curr={current_price:.4f} return={value:.2%}"
            )
        raise AssertionError(
            "Broad-asset monthly return above "
            f"{MONTHLY_RETURN_ASSERTION_THRESHOLD:.0%} detected:\n"
            + "\n".join(details)
        )


def download_polish_cpi() -> pd.Series:
    cached = _read_cached_cpi()
    if cached is not None and _cpi_is_fresh(cached):
        print(
            f"Using cached Polish CPI ({len(cached)} rows, "
            f"{cached.index.min().date()} -> {cached.index.max().date()})."
        )
        return cached

    try:
        cpi = download_polish_cpi_fred(cached)
        _write_cached_cpi(cpi)
        return cpi
    except (requests.RequestException, ValueError) as fred_exc:
        print(f"FRED Polish CPI download failed: {fred_exc}")

    try:
        cpi = download_polish_cpi_world_bank()
        _write_cached_cpi(cpi)
        return cpi
    except (requests.RequestException, ValueError) as wb_exc:
        cached = _read_cached_cpi()
        if cached is not None:
            print(f"World Bank CPI download failed ({wb_exc}).")
            print(f"Using cached CPI through {cached.index.max().date()}.")
            return cached
        print(f"Polish CPI unavailable ({wb_exc}); real metrics will be blank.")
        return pd.Series(dtype=float, name="Polish CPI")


def download_polish_cpi_fred(cached: pd.Series | None = None) -> pd.Series:
    start = pd.Timestamp(START)
    end = last_completed_month_end()
    if cached is not None and not cached.empty:
        start = max(start, cached.index.max() + pd.offsets.MonthBegin(1))

    chunks = [] if cached is None else [cached]
    for chunk_start, chunk_end in cpi_fred_chunks(start, end):
        chunk = download_polish_cpi_fred_chunk(chunk_start, chunk_end)
        if not chunk.empty:
            chunks.append(chunk)

    if not chunks:
        raise ValueError("FRED CPI response contains no numeric observations.")

    cpi = pd.concat(chunks)
    cpi = cpi[~cpi.index.duplicated(keep="last")].sort_index()
    return cpi.rename("Polish CPI")


def cpi_fred_chunks(
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    if start > end:
        return []

    chunks = []
    current = start.normalize()
    while current <= end:
        chunk_end = min(
            current + pd.DateOffset(months=CPI_FRED_CHUNK_MONTHS) - pd.DateOffset(days=1),
            end,
        )
        chunks.append((current, chunk_end))
        current = chunk_end + pd.DateOffset(days=1)

    return chunks


def download_polish_cpi_fred_chunk(
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.Series:
    url = (
        "https://fred.stlouisfed.org/graph/fredgraph.csv"
        f"?id={POLISH_CPI_FRED_SERIES}"
        f"&cosd={start:%Y-%m-%d}"
        f"&coed={end:%Y-%m-%d}"
    )
    last_error: requests.RequestException | None = None
    for _ in range(2):
        try:
            r = requests.get(url, headers=BROWSER_HEADERS, timeout=20)
            r.raise_for_status()
            break
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(1)
    else:
        raise last_error or ValueError("FRED CPI request failed.")

    df = pd.read_csv(io.StringIO(r.text))
    if "observation_date" not in df or POLISH_CPI_FRED_SERIES not in df:
        raise ValueError("FRED CPI response is not the expected CSV format.")

    df["Date"] = pd.to_datetime(df["observation_date"])
    df["CPI"] = pd.to_numeric(df[POLISH_CPI_FRED_SERIES], errors="coerce")
    df = df[(df["Date"] >= start) & (df["Date"] <= end)]
    return df.dropna(subset=["CPI"]).set_index("Date")["CPI"].sort_index()


def download_polish_cpi_world_bank() -> pd.Series:
    r = requests.get(WORLD_BANK_POLISH_CPI_URL, headers=BROWSER_HEADERS, timeout=60)
    r.raise_for_status()
    payload = r.json()
    if not isinstance(payload, list) or len(payload) < 2:
        raise ValueError("World Bank CPI response is not the expected JSON format.")

    rows = [
        {
            "Date": pd.Timestamp(year=int(item["date"]), month=12, day=31),
            "CPI": item["value"],
        }
        for item in payload[1]
        if item.get("value") is not None
    ]
    if not rows:
        raise ValueError("World Bank CPI response contains no CPI values.")

    cpi = pd.DataFrame(rows).set_index("Date")["CPI"].sort_index()
    return cpi.rename("Polish CPI")


def _read_cached_cpi() -> pd.Series | None:
    if not CPI_CACHE_PATH.exists():
        return None
    try:
        df = pd.read_csv(CPI_CACHE_PATH, parse_dates=["Date"], index_col="Date")
        cpi = pd.to_numeric(df["CPI"], errors="coerce").dropna()
    except (OSError, ValueError, KeyError):
        return None
    if cpi.empty:
        return None
    return cpi.sort_index().rename("Polish CPI")


def _cpi_is_fresh(cpi: pd.Series) -> bool:
    latest_allowed = last_completed_month_end() - pd.DateOffset(
        months=CPI_CACHE_MAX_AGE_MONTHS
    )
    return cpi.index.max() >= latest_allowed


def _write_cached_cpi(cpi: pd.Series) -> None:
    PLOT_DIR.mkdir(exist_ok=True)
    cpi.rename("CPI").to_csv(CPI_CACHE_PATH, index_label="Date")


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
        _main = r.json().get("main") or []
        if _main:
            chunk = pd.DataFrame(_main, columns=["ts", "Close"])
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

    tickers = list(ASSETS_7.values()) + [SAFE_BACKFILL_ASSET]
    prices_usd = download_yahoo(tickers)
    safe_eur = download_yahoo([SAFE_ASSET])
    safe_eur.columns = ["Safe"]
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

    # WIG PLN -> EUR
    wig = wig_pln.to_frame()
    wig = wig.join(fx["EURPLN"], how="inner")
    wig["Poland"] = wig["Poland"] / wig["EURPLN"]
    prices_eur = prices_eur.join(wig["Poland"], how="outer")
    safe_backfill = all_daily[SAFE_BACKFILL_ASSET] / all_daily["EURUSD"]

    # ------------------------------------------------
    # MONTH-END DATA
    # ------------------------------------------------

    monthly = prices_eur.resample("ME").last()
    safe = chain_link_prices(
        safe_backfill.resample("ME").last(),
        safe_eur["Safe"].resample("ME").last(),
        "Safe",
    )
    monthly = monthly.join(safe, how="outer")
    monthly = monthly.loc[monthly.index <= last_completed_month_end()]
    monthly = monthly.dropna(subset=list(ASSETS_7.keys()) + ["Safe"])
    return monthly


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
    _drawdown = equity / running_max - 1
    max_dd = _drawdown.min()
    _annual_returns = (1 + r).groupby(r.index.year).prod() - 1
    worst_year = _annual_returns.min()

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


def extended_metrics(
    result: BacktestResult,
    cpi: pd.Series | None = None,
) -> dict[str, float]:
    r = result["returns"].dropna()
    equity = result["equity"].reindex(r.index).dropna()
    years = len(r) / 12
    running_max = equity.cummax()
    drawdowns = equity / running_max - 1
    downside = r[r < 0]
    volatility = r.std() * np.sqrt(12)
    downside_volatility = downside.std() * np.sqrt(12)

    if "turnover" in result:
        turnover_annual = result["turnover"].reindex(r.index).dropna().mean() * 12
    else:
        weights = result["weights"].reindex(r.index).fillna(0)
        turnover_annual = weights.diff().abs().sum(axis=1).mean() * 6

    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1
    real_cagr = np.nan
    real_end_value = np.nan
    if cpi is not None and not cpi.empty:
        real_equity = real_equity_series(equity, cpi)
        if len(real_equity) >= 2:
            real_years = len(real_equity) / 12
            real_cagr = (
                real_equity.iloc[-1] / real_equity.iloc[0]
            ) ** (1 / real_years) - 1
            real_end_value = real_equity.iloc[-1]

    return {
        "CAGR": cagr,
        "Real CAGR": real_cagr,
        "Volatility": volatility,
        "Max Drawdown": drawdowns.min(),
        "Worst Year": annual_return_series(r).min(),
        "Sharpe": cagr / volatility if volatility > 0 else np.nan,
        "Sortino": (
            cagr / downside_volatility
            if pd.notna(downside_volatility) and downside_volatility > 0
            else np.nan
        ),
        "Recovery Months": max_drawdown_recovery_months(equity),
        "End Value": equity.iloc[-1],
        "Real End Value": real_end_value,
        "Annual Turnover": turnover_annual,
    }


def annual_return_series(r: pd.Series) -> pd.Series:
    return (1 + r).groupby(r.index.year).prod() - 1


def real_equity_series(equity: pd.Series, cpi: pd.Series) -> pd.Series:
    cpi_monthly = cpi.resample("ME").last()
    cpi_monthly = cpi_monthly.reindex(cpi_monthly.index.union(equity.index))
    cpi_monthly = cpi_monthly.ffill().reindex(equity.index).dropna()
    aligned_equity = equity.reindex(cpi_monthly.index).dropna()
    cpi_monthly = cpi_monthly.reindex(aligned_equity.index)
    return aligned_equity / (cpi_monthly / cpi_monthly.iloc[0])


def max_drawdown_recovery_months(equity: pd.Series) -> float:
    running_max = equity.cummax()
    drawdowns = equity / running_max - 1
    trough_date = drawdowns.idxmin()
    peak_value = running_max.loc[trough_date]
    recovery = equity.loc[trough_date:]
    recovered = recovery[recovery >= peak_value]
    if recovered.empty:
        return np.nan

    recovery_date = recovered.index[0]
    return (
        (recovery_date.year - trough_date.year) * 12
        + recovery_date.month
        - trough_date.month
    )


def benchmark_result(
    returns: pd.Series,
    label: str,
    weights: pd.DataFrame,
    turnover: pd.Series | None = None,
) -> BacktestResult:
    returns = returns.dropna()
    weights = weights.reindex(returns.index).fillna(0.0)
    result: BacktestResult = {
        "label": label,
        "returns": returns,
        "equity": INITIAL_CAPITAL * (1 + returns).cumprod(),
        "weights": weights,
        "ranking": {},
    }
    if turnover is not None:
        result["turnover"] = turnover.reindex(returns.index).fillna(0.0)
    return result


def weighted_monthly_returns(
    prices: pd.DataFrame,
    weights: dict[str, float],
) -> pd.Series:
    returns = prices[list(weights)].pct_change()
    weights_series = pd.Series(weights)
    return returns.mul(weights_series, axis=1).sum(axis=1, min_count=len(weights))


def price_index_from_returns(
    returns: pd.Series,
    label: str,
) -> pd.Series:
    returns = returns.dropna()
    return (100 * (1 + returns).cumprod()).rename(label)


def build_benchmarks(monthly: pd.DataFrame) -> dict[str, BacktestResult]:
    benchmark_prices = download_yahoo(
        [GLOBAL_EQUITY_BENCHMARK, BOND_EUR_HEDGED_BENCHMARK]
    )

    fx = download_yahoo(["EURUSD=X"])
    fx.columns = ["EURUSD"]

    daily = benchmark_prices.join(fx, how="inner")
    prices_eur = pd.DataFrame(index=daily.index)
    prices_eur["Global Equity B&H"] = (
        daily[GLOBAL_EQUITY_BENCHMARK] / daily["EURUSD"]
    )
    prices_eur["EUR-Hedged Bonds"] = daily[BOND_EUR_HEDGED_BENCHMARK]
    monthly_benchmarks = prices_eur.resample("ME").last().reindex(monthly.index)

    equity_proxy = price_index_from_returns(
        weighted_monthly_returns(monthly, GLOBAL_EQUITY_BACKFILL_WEIGHTS),
        "Global Equity proxy",
    )
    equity_price = chain_link_prices(
        equity_proxy,
        monthly_benchmarks["Global Equity B&H"],
        "Global Equity B&H",
    )
    bond_price = chain_link_prices(
        monthly[BOND_BACKFILL_ASSET],
        monthly_benchmarks["EUR-Hedged Bonds"],
        "EUR-Hedged Bonds",
    )

    benchmark_monthly_prices = pd.DataFrame(
        {
            "Global Equity B&H": equity_price,
            "EUR-Hedged Bonds": bond_price,
        }
    ).reindex(monthly.index)
    diagnose_monthly_returns(benchmark_monthly_prices, "benchmark prices")

    returns = benchmark_monthly_prices.pct_change()
    equity_returns = returns["Global Equity B&H"]
    bond_returns = returns["EUR-Hedged Bonds"]
    benchmark_60_40, turnover_60_40 = monthly_rebalanced_60_40_returns(
        equity_returns,
        bond_returns,
    )

    buy_hold_weights = pd.DataFrame(
        {"Global Equity B&H": 1.0},
        index=equity_returns.dropna().index,
    )
    balanced_weights = pd.DataFrame(
        {"Global Equity B&H": 0.6, "EUR-Hedged Bonds": 0.4},
        index=benchmark_60_40.dropna().index,
    )

    return {
        "All-World Buy & Hold": benchmark_result(
            equity_returns,
            "All-World Buy & Hold",
            buy_hold_weights,
        ),
        "60/40": benchmark_result(
            benchmark_60_40,
            "60/40",
            balanced_weights,
            turnover_60_40,
        ),
    }


def monthly_rebalanced_60_40_returns(
    equity_returns: pd.Series,
    bond_returns: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    joined = pd.concat([equity_returns, bond_returns], axis=1).dropna()
    joined.columns = ["equity", "bonds"]
    returns = 0.6 * joined["equity"] + 0.4 * joined["bonds"]

    equity_drift = 0.6 * (1 + joined["equity"]) / (1 + returns)
    bond_drift = 0.4 * (1 + joined["bonds"]) / (1 + returns)
    turnover = (abs(equity_drift - 0.6) + abs(bond_drift - 0.4)) / 2

    return returns.rename("60/40"), turnover.rename("60/40 Turnover")


def print_strategy_comparison(
    results: dict[str, BacktestResult],
    cpi: pd.Series,
) -> None:
    common_index = None
    for result in results.values():
        idx = result["returns"].dropna().index
        common_index = idx if common_index is None else common_index.intersection(idx)

    if common_index is None or common_index.empty:
        print("\nNo common return history is available for strategy comparison.")
        return

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

    print("\n")
    print("=" * 70)
    print("STRATEGY VS BENCHMARKS")
    print(f"Common nominal period: {common_index.min().date()} -> {common_index.max().date()}")
    cpi_status = cpi.index.max().date() if not cpi.empty else "unavailable"
    print(f"Polish CPI available through: {cpi_status}")
    print(
        "Benchmark backfill: All-World uses "
        f"{display_name('USA')}/{display_name('Europe')}/"
        f"{display_name('Japan')}/{display_name('Emerging Markets')} "
        f"proxy before {GLOBAL_EQUITY_BENCHMARK}; 60/40 bonds use "
        f"{display_name(BOND_BACKFILL_ASSET)} "
        f"before {BOND_EUR_HEDGED_BENCHMARK}."
    )
    print(
        f"Safe backfill: {SAFE_BACKFILL_ASSET} converted to EUR before "
        f"{display_name('Safe')}."
    )
    print("=" * 70)
    print(format_metric_table(comparison))


def align_result_to_index(
    result: BacktestResult,
    index: pd.DatetimeIndex,
) -> BacktestResult:
    returns = result["returns"].reindex(index).dropna()
    aligned_index = returns.index
    aligned: BacktestResult = {
        "label": result["label"],
        "returns": returns,
        "equity": INITIAL_CAPITAL * (1 + returns).cumprod(),
        "weights": result["weights"].reindex(aligned_index).fillna(0.0),
        "ranking": result["ranking"],
    }
    if "turnover" in result:
        aligned["turnover"] = result["turnover"].reindex(aligned_index).fillna(0.0)
    return aligned


def format_metric_table(metrics_frame: pd.DataFrame) -> pd.DataFrame:
    percent_rows = [
        "CAGR",
        "Real CAGR",
        "Volatility",
        "Max Drawdown",
        "Worst Year",
        "Annual Turnover",
    ]
    formatted = metrics_frame.copy().astype(object)
    for row in formatted.index:
        if row in percent_rows:
            formatted.loc[row] = formatted.loc[row].map(
                lambda x: "" if pd.isna(x) else f"{x:.2%}"
            )
        elif row in ["Sharpe", "Sortino"]:
            formatted.loc[row] = formatted.loc[row].map(
                lambda x: "" if pd.isna(x) else f"{x:.2f}"
            )
        elif row == "Recovery Months":
            formatted.loc[row] = formatted.loc[row].map(
                lambda x: "Not recovered" if pd.isna(x) else f"{x:.0f}"
            )
        elif row in ["End Value", "Real End Value"]:
            formatted.loc[row] = formatted.loc[row].map(
                lambda x: "" if pd.isna(x) else f"{x:,.0f}"
            )
    return formatted


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


def last_completed_month_end(as_of: pd.Timestamp | None = None) -> pd.Timestamp:
    today = (as_of or pd.Timestamp.today()).normalize()
    current_month_end = today + pd.offsets.MonthEnd(0)
    if today < current_month_end:
        return today + pd.offsets.MonthEnd(-1)
    return current_month_end
