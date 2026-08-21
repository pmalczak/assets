# -*- coding: utf-8 -*-
"""Wspólna kontrola luk w pokryciu okresów wyciągów."""
from __future__ import annotations

from datetime import date, timedelta


def merge_coverage(periods: list[tuple[date, date]]) -> list[tuple[date, date]]:
    """Scala nachodzące i stykające się okresy (next.start ≤ prev.end + 1 dzień)."""
    if not periods:
        return []
    ordered = sorted(periods, key=lambda p: (p[0], p[1]))
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end + timedelta(days=1):
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def find_coverage_gaps(periods: list[tuple[date, date]]) -> list[tuple[date, date]]:
    """Brakujące dni (domknięty przedział) między scalonymi okresami."""
    merged = merge_coverage(periods)
    gaps: list[tuple[date, date]] = []
    for prev, nxt in zip(merged, merged[1:]):
        gap_start = prev[1] + timedelta(days=1)
        gap_end = nxt[0] - timedelta(days=1)
        if gap_start <= gap_end:
            gaps.append((gap_start, gap_end))
    return gaps


def assert_no_coverage_gaps(
    periods: list[tuple[date, date]],
    *,
    asset_id: str = "",
    label: str = "wyciąg",
) -> None:
    """Po scaleniu okresów: luka między wyciągami → twardy błąd."""
    gaps = find_coverage_gaps(periods)
    if not gaps:
        return
    gap_start, gap_end = gaps[0]
    prev_end = gap_start - timedelta(days=1)
    next_start = gap_end + timedelta(days=1)
    prefix = f"[{asset_id}] " if asset_id else ""
    raise ValueError(
        f"{prefix}Luka w pokryciu {label}: "
        f"{prev_end.isoformat()} .. {next_start.isoformat()} "
        f"(brak cash-flow między wyciągami)"
    )
