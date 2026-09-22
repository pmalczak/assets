# -*- coding: utf-8 -*-
"""Ceny złota NBP: PLN za 1 g próby 1000 (api.nbp.pl/api/cenyzlota)."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import requests

NBP_GOLD_HISTORY_START = date(2013, 1, 2)
NBP_GOLD_MAX_RANGE_DAYS = 93
NBP_GOLD_DATE = "data"
NBP_GOLD_PRICE = "cena"


def fetch_nbp_gold(start: date, end: date) -> pd.DataFrame:
    """Seria dzienna od start do end włącznie. Puste okno (404) jest pomijane."""
    if end < start:
        raise ValueError(f"Zakres cen złota NBP jest pusty: {start} > {end}.")

    frames: list[pd.DataFrame] = []
    for chunk_start, chunk_end in _date_chunks(start, end, NBP_GOLD_MAX_RANGE_DAYS):
        chunk = _fetch_chunk(chunk_start, chunk_end)
        if not chunk.empty:
            frames.append(chunk)
    if not frames:
        raise ValueError(f"Brak cen złota NBP od {start.isoformat()} do {end.isoformat()}.")

    series = pd.concat(frames, ignore_index=True)
    series = series.drop_duplicates(subset=[NBP_GOLD_DATE], keep="last")
    series = series.sort_values(NBP_GOLD_DATE).reset_index(drop=True)
    return series


def _date_chunks(start: date, end: date, max_days: int):
    cursor = start
    while cursor <= end:
        chunk_end = min(end, cursor + timedelta(days=max_days - 1))
        yield cursor, chunk_end
        cursor = chunk_end + timedelta(days=1)


def _fetch_chunk(start: date, end: date) -> pd.DataFrame:
    url = (
        "https://api.nbp.pl/api/cenyzlota/"
        f"{start.isoformat()}/{end.isoformat()}/?format=json"
    )
    response = requests.get(url, timeout=30)
    if response.status_code == 404:
        return pd.DataFrame(columns=[NBP_GOLD_DATE, NBP_GOLD_PRICE])
    if response.status_code != 200:
        raise ReferenceError(f"{url} / {response.content!r}")

    payload = response.json()
    frame = pd.DataFrame(payload)
    if frame.empty:
        return pd.DataFrame(columns=[NBP_GOLD_DATE, NBP_GOLD_PRICE])
    frame[NBP_GOLD_DATE] = pd.to_datetime(frame[NBP_GOLD_DATE]).dt.normalize()
    frame[NBP_GOLD_PRICE] = pd.to_numeric(frame[NBP_GOLD_PRICE], errors="coerce")
    return frame[[NBP_GOLD_DATE, NBP_GOLD_PRICE]]
