# -*- coding: utf-8 -*-
"""Wspólna kontrola luk w pokryciu okresów wyciągów."""
from __future__ import annotations

from datetime import date, timedelta


def assert_no_coverage_gaps(
    periods: list[tuple[date, date]],
    *,
    asset_id: str = "",
    label: str = "wyciąg",
) -> None:
    """Po posortowaniu okresów: next.start > prev.end + 1 day → twardy błąd."""
    if len(periods) <= 1:
        return
    ordered = sorted(periods, key=lambda p: (p[0], p[1]))
    for prev, nxt in zip(ordered, ordered[1:]):
        expected_next = prev[1] + timedelta(days=1)
        if nxt[0] > expected_next:
            prefix = f"[{asset_id}] " if asset_id else ""
            raise ValueError(
                f"{prefix}Luka w pokryciu {label}: "
                f"{prev[1].isoformat()} .. {nxt[0].isoformat()} "
                f"(brak cash-flow między wyciągami)"
            )
