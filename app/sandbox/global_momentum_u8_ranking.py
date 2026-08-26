# ================================================================
# GLOBAL MOMENTUM U7 RANKING
# Operational monthly portfolio selection
# ================================================================

import io

import pandas as pd
import requests

from sandbox.global_momentum_common import (
    BROWSER_HEADERS,
    MOMENTUM_PERIODS,
    SMA_MONTHS,
    START,
    TOP_N,
    chain_link_prices,
    download_yahoo,
    download_wig,
    display_name,
    last_completed_month_end,
    momentum_score,
)

RANKING_TICKERS = {
    "USA": "SXR8.DE",
    "Europe": "EUNK.DE",
    "Japan": "EUNN.DE",
    "Emerging Markets": "IS3N.DE",
    "Bonds": "EUNA.DE",
    "Commodities": "SXRS.DE",
    # Yahoo Finance uses the Warsaw suffix .WA for this GPW-listed ETF.
    "Poland": "ETFPZUW20M40.WA",
}
POLAND_PROXY_WEIGHTS = {
    "WIG20TR": 0.5,
    "MWIG40TR": 0.5,
}
POLAND_PROXY_BIZNESRADAR_SYMBOLS = {
    "WIG20TR": "WIG20TR",
    "MWIG40TR": "mWIG40TR",
}


def last_common_close_date(daily: pd.DataFrame) -> pd.Timestamp | None:
    if daily.empty or daily.shape[1] == 0:
        return None
    complete = daily.dropna(how="any")
    if complete.empty:
        return None
    return pd.Timestamp(complete.index.max())


def with_partial_month_stub(
    completed_monthly: pd.DataFrame,
    daily: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Timestamp | None]:
    columns = list(completed_monthly.columns)
    as_of = last_common_close_date(daily[columns])
    if as_of is None:
        return completed_monthly.iloc[0:0], None
    month_end = last_completed_month_end()
    as_of_day = pd.Timestamp(as_of).normalize()
    if as_of_day <= pd.Timestamp(month_end).normalize():
        return completed_monthly, as_of_day
    row = daily.loc[as_of, columns]
    if isinstance(row, pd.DataFrame):
        row = row.iloc[-1]
    stub = row.to_frame().T
    stub.index = pd.DatetimeIndex([as_of_day])
    return pd.concat([completed_monthly, stub]), as_of_day


def load_current_ranking_prices(
    _start,
    include_partial_month: bool = False,
) -> pd.DataFrame:
    tickers = list(RANKING_TICKERS.values())
    daily = download_yahoo(tickers, start=_start)
    missing_tickers = [
        ticker
        for ticker in tickers
        if ticker not in daily.columns or daily[ticker].dropna().empty
    ]
    if missing_tickers:
        raise ValueError(
            "No price history returned for ranking ticker(s): "
            + ", ".join(missing_tickers)
        )

    prices = pd.DataFrame(
        {
            asset: daily[ticker]
            for asset, ticker in RANKING_TICKERS.items()
        }
    )
    monthly = prices.resample("ME").last()
    monthly["Poland"] = build_poland_execution_series(monthly["Poland"])
    completed = monthly.loc[monthly.index <= last_completed_month_end()]
    if not include_partial_month:
        return completed
    stubbed, _as_of = with_partial_month_stub(completed, prices)
    return stubbed


def build_poland_execution_series(etf_monthly: pd.Series) -> pd.Series:
    actual = pd.to_numeric(etf_monthly, errors="coerce").dropna().sort_index()
    if actual.empty:
        raise ValueError(f"No price history returned for {RANKING_TICKERS['Poland']}.")

    try:
        proxy = build_poland_benchmark_proxy()
        proxy_label = "proxy 50% WIG20TR + 50% mWIG40TR"
    except (requests.RequestException, ValueError, KeyError) as exc:
        print(
            "WARNING: Could not obtain reliable WIG20TR/mWIG40TR data for "
            f"Poland execution proxy ({exc}). Falling back to broad WIG, "
            "which does not exactly match the ETF benchmark."
        )
        proxy = download_wig().resample("ME").last()
        proxy_label = "fallback broad WIG proxy"

    linked = chain_link_prices(proxy, actual, "Poland")
    splice_date = actual.index.min()
    proxy_through = splice_date + pd.offsets.MonthEnd(-1)
    print(
        "Poland execution series: "
        f"{proxy_label} through {proxy_through.date()}, "
        f"actual {RANKING_TICKERS['Poland']} from {splice_date.date()}"
    )
    return linked.rename("Poland")


def build_poland_benchmark_proxy() -> pd.Series:
    monthly_indexes = pd.DataFrame(
        {
            symbol: download_poland_proxy_index(symbol).resample("ME").last()
            for symbol in POLAND_PROXY_WEIGHTS
        }
    ).dropna()
    if monthly_indexes.empty:
        raise ValueError("Bankier returned no overlapping WIG20TR/MWIG40TR history.")

    monthly_returns = monthly_indexes.pct_change().dropna()
    portfolio_returns = sum(
        weight * monthly_returns[symbol]
        for symbol, weight in POLAND_PROXY_WEIGHTS.items()
    )
    proxy = 100 * (1 + portfolio_returns).cumprod()
    return proxy.rename("Poland benchmark proxy")


def download_poland_proxy_index(symbol: str) -> pd.Series:
    pieces: list[pd.Series] = []
    bankier = download_bankier_index(symbol)
    if not bankier.empty:
        pieces.append(bankier)

    stop_before = bankier.index.max() if not bankier.empty else None
    biznesradar_symbol = POLAND_PROXY_BIZNESRADAR_SYMBOLS[symbol]
    biznesradar = download_biznesradar_index(
        biznesradar_symbol,
        stop_before=stop_before,
    )
    if not biznesradar.empty:
        pieces.append(biznesradar.rename(symbol))

    if not pieces:
        raise ValueError(f"No data returned for {symbol}.")

    close = pd.concat(pieces)
    close = close[~close.index.duplicated(keep="last")].sort_index()
    close = pd.to_numeric(close, errors="coerce").dropna()
    return close.loc[close.index >= START].rename(symbol)


def download_bankier_index(symbol: str) -> pd.Series:
    session = requests.Session()
    session.headers.update(
        {
            **BROWSER_HEADERS,
            "Accept": "application/json,text/plain,*/*",
            "Referer": (
                "https://www.bankier.pl/inwestowanie/profile/quote.html"
                f"?symbol={symbol}"
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
                year=chunk_end_year,
                month=12,
                day=31,
                tz="UTC",
            ).timestamp()
            * 1000
        )
        url = (
            "https://www.bankier.pl/new-charts/get-data"
            f"?symbol={symbol}&date_from={date_from}&date_to={date_to}"
            "&intraday=false&type=area"
        )
        response = session.get(url, timeout=30)
        response.raise_for_status()
        points = response.json().get("main") or []
        if points:
            chunk = pd.DataFrame(points, columns=["ts", "Close"])
            chunk["Date"] = pd.to_datetime(
                chunk["ts"],
                unit="ms",
                utc=True,
            ).dt.tz_convert(None)
            frames.append(chunk.set_index("Date")["Close"])
        year = chunk_end_year + 1

    if not frames:
        raise ValueError(f"Bankier chart API returned no {symbol} points.")

    close = pd.concat(frames)
    close = close[~close.index.duplicated(keep="last")].sort_index()
    close = pd.to_numeric(close, errors="coerce").dropna()
    return close.loc[close.index >= START].rename(symbol)


def download_biznesradar_index(
    symbol: str,
    stop_before: pd.Timestamp | None = None,
) -> pd.Series:
    session = requests.Session()
    session.headers.update(BROWSER_HEADERS)
    cutoff = (
        pd.Timestamp(stop_before)
        if stop_before is not None
        else pd.Timestamp(START)
    )
    base_url = f"https://www.biznesradar.pl/notowania-historyczne/{symbol}"
    frames: list[pd.Series] = []

    for page in range(1, 201):
        url = base_url if page == 1 else f"{base_url},{page}"
        response = session.get(url, timeout=30)
        response.raise_for_status()
        tables = pd.read_html(
            io.StringIO(response.text),
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

    if not frames:
        raise ValueError(f"Biznesradar returned no {symbol} rows.")

    close = pd.concat(frames)
    close = close[~close.index.duplicated(keep="last")].sort_index()
    close = pd.to_numeric(close, errors="coerce").dropna()
    return close.loc[close.index >= START].rename(symbol)


def compute_current_universe7_ranking(
    monthly: pd.DataFrame,
    universe7: list[str],
    as_of_limit: pd.Timestamp | None = None,
) -> dict:
    prices = monthly[universe7]
    returns_by_period = {
        f"{months}M": prices / prices.shift(months) - 1
        for months in MOMENTUM_PERIODS
    }
    momentum = momentum_score(prices)
    sma = prices.rolling(SMA_MONTHS).mean()

    required = pd.concat(
        [
            prices.notna().all(axis=1),
            momentum.notna().all(axis=1),
            sma.notna().all(axis=1),
        ],
        axis=1,
    )
    latest_full_month = last_completed_month_end()
    signal_cutoff = as_of_limit if as_of_limit is not None else latest_full_month
    signal_dates = required[required.all(axis=1)].index
    signal_dates = signal_dates[signal_dates <= signal_cutoff]
    if signal_dates.empty:
        availability_rows = []
        for asset in universe7:
            history = prices[asset].dropna()
            ready_dates = (
                prices[asset].notna()
                & momentum[asset].notna()
                & sma[asset].notna()
            )
            ready_dates = ready_dates[ready_dates].index
            ready_dates = ready_dates[ready_dates <= signal_cutoff]
            availability_rows.append(
                {
                    "Asset": display_name(asset),
                    "Ticker": RANKING_TICKERS[asset],
                    "First": history.index.min().date() if not history.empty else None,
                    "Last": history.index.max().date() if not history.empty else None,
                    "Months": len(history),
                    "Ready Through": (
                        ready_dates.max().date() if not ready_dates.empty else None
                    ),
                }
            )
        return {
            "ready": False,
            "latest_full_month": latest_full_month.date(),
            "min_observations": max(max(MOMENTUM_PERIODS) + 1, SMA_MONTHS),
            "availability": pd.DataFrame(availability_rows),
        }

    signal_date = signal_dates[-1]
    ranking = momentum.loc[signal_date].dropna().sort_values(ascending=False)
    top_assets = list(ranking.head(TOP_N).index)
    weight = 1 / TOP_N
    safe_weight = 0.0
    allocation: dict[str, float] = {}
    ranking_rows = []

    for rank, asset in enumerate(ranking.index, start=1):
        price = prices.loc[signal_date, asset]
        sma10 = sma.loc[signal_date, asset]
        trend = "PASS" if price > sma10 else "FAIL"
        is_top = asset in top_assets

        if is_top and trend == "PASS":
            allocation[asset] = weight
        elif is_top:
            safe_weight += weight

        ranking_rows.append(
            {
                "Rank": rank,
                "Asset": display_name(asset),
                "3M": returns_by_period["3M"].loc[signal_date, asset],
                "6M": returns_by_period["6M"].loc[signal_date, asset],
                "12M": returns_by_period["12M"].loc[signal_date, asset],
                "Score": ranking.loc[asset],
                "Price": price,
                "SMA10": sma10,
                "Trend": trend,
                "TOP3": is_top,
            }
        )

    allocation_rows = [
        {"Asset": display_name(asset), "Weight": allocation.get(asset, 0.0)}
        for asset in top_assets
    ]
    allocation_rows.append({"Asset": display_name("Safe"), "Weight": safe_weight})
    return {
        "ready": True,
        "signal_date": signal_date.date(),
        "ranking": pd.DataFrame(ranking_rows),
        "allocation": pd.DataFrame(allocation_rows),
    }


def top3_drift_marker(*, was_top: bool, is_top: bool) -> str:
    if is_top and was_top:
        return "*"
    if is_top and not was_top:
        return "+"
    if was_top and not is_top:
        return "-"
    return ""


def annotate_asset_top3_drift(
    ranking: pd.DataFrame,
    previous_ranking: pd.DataFrame,
) -> pd.DataFrame:
    previous_top = set(
        previous_ranking.loc[previous_ranking["TOP3"].astype(bool), "Asset"]
    )
    annotated = ranking.copy()
    markers = [
        top3_drift_marker(was_top=row["Asset"] in previous_top, is_top=bool(row["TOP3"]))
        for row in annotated.to_dict("records")
    ]
    annotated["Asset"] = [
        f"{marker} {name}" if marker else name
        for marker, name in zip(markers, annotated["Asset"])
    ]
    return annotated


def compute_current_universe8_ranking(
    monthly: pd.DataFrame,
    universe8: list[str],
    as_of_limit: pd.Timestamp | None = None,
) -> dict:
    return compute_current_universe7_ranking(
        monthly,
        universe8,
        as_of_limit=as_of_limit,
    )


def run_u7_ranking(*, include_partial_month: bool = False) -> dict:
    monthly = load_current_ranking_prices(
        START,
        include_partial_month=include_partial_month,
    )
    no_common_close = include_partial_month and monthly.empty
    as_of_limit = (
        monthly.index.max()
        if not monthly.empty
        else last_completed_month_end()
    )
    universe = list(RANKING_TICKERS.keys())
    result = compute_current_universe7_ranking(
        monthly,
        universe,
        as_of_limit=as_of_limit,
    )
    result["is_nowcast"] = include_partial_month
    result["no_common_close"] = no_common_close
    if include_partial_month and result["ready"]:
        official = compute_current_universe7_ranking(
            monthly.loc[monthly.index <= last_completed_month_end()],
            universe,
            as_of_limit=last_completed_month_end(),
        )
        if official["ready"]:
            result["ranking"] = annotate_asset_top3_drift(
                result["ranking"],
                official["ranking"],
            )
    return result


def run_u8_ranking() -> dict:
    return run_u7_ranking()


def print_current_universe7_ranking(
    monthly: pd.DataFrame,
    universe7: list[str],
) -> None:
    result = compute_current_universe7_ranking(monthly, universe7)
    if not result["ready"]:
        print("\nNo complete Universe 7 signal date is available using execution ETF prices.")
        print(f"Latest completed month: {result['latest_full_month']}")
        print(
            "Minimum required month-end observations per asset: "
            f"{result['min_observations']}"
        )
        print("\nData availability:")
        availability = result["availability"]
        asset_width = max(32, *(len(str(name)) for name in availability["Asset"]))
        print(
            f"{'Asset':<{asset_width}} {'Ticker':<18} {'First':<10} "
            f"{'Last':<10} {'Months':>6} {'Ready Through':<13}"
        )
        for row in availability.to_dict("records"):
            first = row["First"] if row["First"] is not None else "n/a"
            last = row["Last"] if row["Last"] is not None else "n/a"
            ready_through = row["Ready Through"]
            ready_through = ready_through if ready_through is not None else "not ready"
            print(
                f"{row['Asset']:<{asset_width}} "
                f"{row['Ticker']:<18} "
                f"{str(first):<10} {str(last):<10} "
                f"{row['Months']:>6} {str(ready_through):<13}"
            )
        return

    ranking = result["ranking"]
    asset_width = max(32, *(len(str(name)) for name in ranking["Asset"]))
    print("\n")
    print("=" * 70)
    print("CURRENT UNIVERSE 7 RANKING")
    print(f"Signal date: {result['signal_date']}")
    print("=" * 70)
    print(
        f"{'Rank':<5} {'Asset':<{asset_width}} {'3M':>8} {'6M':>8} {'12M':>8} "
        f"{'Score':>8} {'Price':>10} {'SMA10':>10} {'Trend':>7} {'TOP3':>5}"
    )
    for row in ranking.to_dict("records"):
        print(
            f"{row['Rank']:<5} {row['Asset']:<{asset_width}} "
            f"{row['3M']:>8.2%} "
            f"{row['6M']:>8.2%} "
            f"{row['12M']:>8.2%} "
            f"{row['Score']:>8.2%} "
            f"{row['Price']:>10.2f} "
            f"{row['SMA10']:>10.2f} "
            f"{row['Trend']:>7} "
            f"{'*' if row['TOP3'] else '':>5}"
        )

    print("\n")
    print("=" * 70)
    print("CURRENT TOP3 ALLOCATION")
    print("=" * 70)
    allocation = result["allocation"]
    allocation_width = max(asset_width, *(len(str(name)) for name in allocation["Asset"]))
    for row in allocation.to_dict("records"):
        print(f"{row['Asset']:<{allocation_width}} {row['Weight']:>8.2%}")


def main() -> None:
    monthly = load_current_ranking_prices(START)
    print_current_universe7_ranking(monthly, list(RANKING_TICKERS.keys()))


def print_current_universe8_ranking(
    monthly: pd.DataFrame,
    universe8: list[str],
) -> None:
    print_current_universe7_ranking(monthly, universe8)


if __name__ == "__main__":
    main()
