# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from datetime import date

YAHOO_STEP = "yahoo"
CLOSE = "Close"
DEFAULT_START = "2006-01-01"

_UNSAFE_TICKER = re.compile(r"[^A-Za-z0-9._-]")


def safe_ticker(ticker: str) -> str:
    name = ticker.strip()
    if not name:
        raise ValueError("ticker must not be empty")
    return _UNSAFE_TICKER.sub("_", name)


def as_of_date(end: str | None) -> date:
    if end is None:
        return date.today()
    parsed = date.fromisoformat(end)
    return parsed


def yahoo_ticker_resource(ticker: str, as_of: date) -> str:
    return f"{YAHOO_STEP}/{safe_ticker(ticker)}/{as_of:%Y-%m-%d}.parquet"
