# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date

import pandas as pd

from data_step.data_step import DATA_STEP
from data_step.data_strep_data_types import REFRESHED
from yahoo_finance.data_model import (
    CLOSE,
    DEFAULT_START,
    as_of_date,
    yahoo_ticker_resource,
)
from yahoo_finance.fetch import fetch_yahoo_close


def download_yahoo(
    tickers: list[str],
    start: str = DEFAULT_START,
    end: str | None = None,
) -> pd.DataFrame:
    if not tickers:
        raise ValueError("tickers must not be empty")

    as_of = as_of_date(end)
    series: list[pd.Series] = []
    for ticker in tickers:
        product = yahoo_ticker_resource(ticker, as_of)
        result = DATA_STEP.obtain(
            product,
            _collect_yahoo_ticker,
            ticker=ticker,
            start=start,
            end=end,
        )
        series.append(_close_series(result.data_frame(), ticker))
        if result.get_status() == REFRESHED:
            _delete_outdated_as_of(ticker, as_of)

    out = pd.concat(series, axis=1)
    out.index = pd.to_datetime(out.index)
    return out


def _collect_yahoo_ticker(
    ticker: str,
    start: str,
    end: str | None = None,
    **_kwargs,
) -> pd.DataFrame:
    return fetch_yahoo_close(ticker, start=start, end=end)


def _close_series(frame: pd.DataFrame, ticker: str) -> pd.Series:
    if ticker in frame.columns:
        values = frame[ticker]
    elif CLOSE in frame.columns:
        values = frame[CLOSE]
    elif len(frame.columns) == 1:
        values = frame.iloc[:, 0]
    else:
        raise ValueError(f"No Close series for {ticker}.")
    return pd.to_numeric(values, errors="coerce").rename(ticker)


def _delete_outdated_as_of(ticker: str, keep_as_of: date) -> None:
    keep = yahoo_ticker_resource(ticker, keep_as_of)
    keep_path = DATA_STEP.get_absolute_file_path(keep)
    ticker_dir = keep_path.parent
    if not ticker_dir.is_dir():
        return
    for path in ticker_dir.glob("*.parquet"):
        if path.name == keep_path.name:
            continue
        path.unlink(missing_ok=True)
        DATA_STEP.metadata.delete(
            yahoo_ticker_resource(ticker, date.fromisoformat(path.stem))
        )
