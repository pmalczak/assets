# -*- coding: utf-8 -*-
"""Metryki ścieżki NAV (dowolny portfel) i wspólne rebase dwóch serii."""
from __future__ import annotations

import pandas as pd


def _drawdown(equity: pd.Series) -> pd.Series:
    return equity / equity.cummax() - 1


def nav_path_metrics(nav: pd.Series) -> dict[str, float]:
    clean = pd.to_numeric(nav, errors="coerce").dropna()
    clean = clean[clean > 0]
    if len(clean) < 2:
        return {}
    start = float(clean.iloc[0])
    end = float(clean.iloc[-1])
    days = (clean.index[-1] - clean.index[0]).days
    years = days / 365.25 if days > 0 else 0.0
    total_return = end / start - 1.0
    metrics = {
        "Total Return": total_return,
        "Max Drawdown": float(_drawdown(clean).min()),
        "Start": start,
        "End": end,
    }
    if years > 0:
        metrics["CAGR"] = (end / start) ** (1.0 / years) - 1.0
    return metrics


def rebased_overlap(left: pd.Series, right: pd.Series) -> pd.DataFrame:
    a = pd.to_numeric(left, errors="coerce").dropna()
    b = pd.to_numeric(right, errors="coerce").dropna()
    a.index = pd.to_datetime(a.index)
    b.index = pd.to_datetime(b.index)
    if a.empty or b.empty:
        return pd.DataFrame()
    start = max(a.index.min(), b.index.min())
    end = min(a.index.max(), b.index.max())
    if start > end:
        return pd.DataFrame()
    idx = a.index.union(b.index).sort_values()
    idx = idx[(idx >= start) & (idx <= end)]
    combined = pd.DataFrame(
        {
            str(a.name or "left"): a.reindex(idx).ffill(),
            str(b.name or "right"): b.reindex(idx).ffill(),
        }
    ).dropna()
    if combined.empty:
        return combined
    return combined / combined.iloc[0] * 100.0
