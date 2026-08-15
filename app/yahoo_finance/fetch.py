# -*- coding: utf-8 -*-
from __future__ import annotations

import pandas as pd
import yfinance as yf

from yahoo_finance.data_model import CLOSE


def fetch_yahoo_close(
    ticker: str,
    start: str,
    end: str | None = None,
) -> pd.DataFrame:
    data = yf.download(
        ticker,
        start=start,
        end=end,
        auto_adjust=True,
        progress=False,
        group_by="column",
    )
    close = _extract_close(data, ticker)
    close = close.dropna()
    if close.empty:
        raise ValueError(f"No price history returned for {ticker}.")
    return close


def _extract_close(data: pd.DataFrame | pd.Series, ticker: str) -> pd.DataFrame:
    if data is None or (isinstance(data, pd.DataFrame) and data.empty):
        raise ValueError(f"No price history returned for {ticker}.")

    if isinstance(data, pd.Series):
        close = data.to_frame(ticker)
    elif CLOSE in data.columns:
        close_data = data[CLOSE]
        if isinstance(close_data, pd.Series):
            close = close_data.to_frame(ticker)
        else:
            close = close_data.copy()
            if ticker in close.columns:
                close = close[[ticker]]
            elif len(close.columns) == 1:
                close.columns = [ticker]
            else:
                raise ValueError(f"No Close series for {ticker}.")
    elif len(data.columns) == 1:
        close = data.copy()
        close.columns = [ticker]
    else:
        raise ValueError(f"No Close series for {ticker}.")

    close.index = _naive_index(close.index)
    return close


def _naive_index(index: pd.Index) -> pd.DatetimeIndex:
    idx = pd.to_datetime(index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    return idx
