# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

import pandas as pd

from importers.degiro.data_model import (
    ACCOUNT_PREFIX,
    ACCOUNT_SOURCE,
    DEFAULT_DEGIRO_ASSET_ID,
    PORTFOLIO_PREFIX,
    PORTFOLIO_SOURCE,
    TRANSACTIONS_PREFIX,
    TRANSACTIONS_SOURCE,
    DegiroAccountFile,
    DegiroTransactionsFile,
)
from importers.degiro.read_degiro import (
    dated_filename,
    period_from_account_file,
    read_account_csv,
    read_portfolio_csv,
    read_transactions_csv,
)
from maintenance.move_downloaded_results import (
    ACTION_MOVED,
    ACTION_SKIPPED,
    KIND_DEGIRO,
    MoveResult,
)

_SOURCES = {
    PORTFOLIO_SOURCE: PORTFOLIO_PREFIX,
    TRANSACTIONS_SOURCE: TRANSACTIONS_PREFIX,
    ACCOUNT_SOURCE: ACCOUNT_PREFIX,
}


def move_degiro_files(assets_root: Path, download: Path) -> list[MoveResult]:
    """Przenosi pakiet DEGIRO Portfolio/Transactions/Account z Downloads do assets/p_degiro."""
    existing_sources = [download / name for name in _SOURCES if (download / name).is_file()]
    if not existing_sources:
        return []
    if len(existing_sources) != len(_SOURCES):
        missing = sorted(name for name in _SOURCES if not (download / name).is_file())
        present = sorted(path.name for path in existing_sources)
        raise ValueError(
            f"Niekompletny pakiet DEGIRO w {download}: jest {present}, brakuje {missing}"
        )

    account_src = download / ACCOUNT_SOURCE
    period_start, period_end = period_from_account_file(account_src)
    target_dir = assets_root / DEFAULT_DEGIRO_ASSET_ID
    target_dir.mkdir(parents=True, exist_ok=True)

    targets = {
        source_name: target_dir / dated_filename(prefix, period_start, period_end)
        for source_name, prefix in _SOURCES.items()
    }
    decision = _resolve_existing_targets(download, targets)
    if decision == "skip":
        for source_name in _SOURCES:
            (download / source_name).unlink()
        return [
            MoveResult(
                source=download / source_name,
                destination=targets[source_name],
                action=ACTION_SKIPPED,
                kind=KIND_DEGIRO,
            )
            for source_name in sorted(_SOURCES)
        ]
    if decision == "conflict":
        raise ValueError(
            f"Konflikt treści DEGIRO dla okresu "
            f"{period_start.isoformat()}..{period_end.isoformat()} w {target_dir}"
        )

    results: list[MoveResult] = []
    for source_name in sorted(_SOURCES):
        src = download / source_name
        dst = targets[source_name]
        src.replace(dst)
        results.append(
            MoveResult(
                source=src,
                destination=dst,
                action=ACTION_MOVED,
                kind=KIND_DEGIRO,
            )
        )
    return results


def _resolve_existing_targets(download: Path, targets: dict[str, Path]) -> str:
    existing = {name: target for name, target in targets.items() if target.is_file()}
    if not existing:
        return "move"
    if len(existing) != len(targets):
        return "conflict"

    if _portfolio_equal(existing[PORTFOLIO_SOURCE], download / PORTFOLIO_SOURCE) and _records_cover(
        read_transactions_csv(existing[TRANSACTIONS_SOURCE]),
        read_transactions_csv(download / TRANSACTIONS_SOURCE),
        DegiroTransactionsFile.unique_key(),
    ) and _records_cover(
        read_account_csv(existing[ACCOUNT_SOURCE]),
        read_account_csv(download / ACCOUNT_SOURCE),
        DegiroAccountFile.unique_key(),
    ):
        return "skip"
    return "conflict"


def _portfolio_equal(existing: Path, incoming: Path) -> bool:
    old = read_portfolio_csv(existing).fillna("")
    new = read_portfolio_csv(incoming).fillna("")
    return old.astype(str).equals(new.astype(str))


def _records_cover(existing: pd.DataFrame, incoming: pd.DataFrame, key_cols: list[str]) -> bool:
    if incoming.empty:
        return True
    old_keys = _key_set(existing, key_cols)
    new_keys = _key_set(incoming, key_cols)
    return new_keys <= old_keys


def _key_set(df: pd.DataFrame, key_cols: list[str]) -> set[tuple[str, ...]]:
    if df.empty:
        return set()
    frame = df.loc[:, key_cols].copy().fillna("")
    for col in key_cols:
        frame[col] = frame[col].map(str)
    return {tuple(row) for row in frame.itertuples(index=False, name=None)}
