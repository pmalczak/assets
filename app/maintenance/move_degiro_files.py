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
from importers.statement_download_date import download_date_of
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

# Account/Transactions covered; Portfolio may refresh (same od..do, newer MTM).
_DECISION_SKIP = "skip"
_DECISION_MOVE = "move"
_DECISION_REPLACE_PORTFOLIO = "replace_portfolio"
_DECISION_REPLACE_PACKAGE = "replace_package"
_DECISION_CONFLICT = "conflict"


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
    fetched = download_date_of(account_src)
    target_dir = assets_root / DEFAULT_DEGIRO_ASSET_ID
    target_dir.mkdir(parents=True, exist_ok=True)

    existing = {
        source_name: _existing_period_file(target_dir, prefix, period_start, period_end)
        for source_name, prefix in _SOURCES.items()
    }
    if all(path is not None for path in existing.values()):
        decision = _resolve_existing_targets(download, existing)
        targets = existing
    else:
        decision = _DECISION_MOVE
        targets = {
            source_name: target_dir / dated_filename(prefix, period_start, period_end, fetched)
            for source_name, prefix in _SOURCES.items()
        }

    if decision == _DECISION_SKIP:
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

    if decision == _DECISION_CONFLICT:
        raise ValueError(
            f"Konflikt treści DEGIRO dla okresu "
            f"{period_start.isoformat()}..{period_end.isoformat()} w {target_dir}"
        )

    if decision == _DECISION_REPLACE_PORTFOLIO:
        return _replace_portfolio_only(
            download,
            target_dir,
            existing,
            period_start=period_start,
            period_end=period_end,
            fetched=fetched,
        )

    if decision == _DECISION_REPLACE_PACKAGE:
        _delete_period_files(target_dir, period_start, period_end)
        targets = {
            source_name: target_dir / dated_filename(prefix, period_start, period_end, fetched)
            for source_name, prefix in _SOURCES.items()
        }

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


def _existing_period_file(
    target_dir: Path, prefix: str, period_start, period_end
) -> Path | None:
    matches = sorted(
        target_dir.glob(f"{prefix}_{period_start.isoformat()}_{period_end.isoformat()}*.csv")
    )
    return matches[0] if matches else None


def _delete_period_files(target_dir: Path, period_start, period_end) -> None:
    pattern = f"*_{period_start.isoformat()}_{period_end.isoformat()}*.csv"
    for path in target_dir.glob(pattern):
        if path.is_file():
            path.unlink()


def _resolve_existing_targets(download: Path, targets: dict[str, Path]) -> str:
    existing = {name: target for name, target in targets.items() if target.is_file()}
    if not existing:
        return _DECISION_MOVE
    if len(existing) != len(targets):
        return _DECISION_CONFLICT

    existing_tx = read_transactions_csv(existing[TRANSACTIONS_SOURCE])
    incoming_tx = read_transactions_csv(download / TRANSACTIONS_SOURCE)
    existing_acc = read_account_csv(existing[ACCOUNT_SOURCE])
    incoming_acc = read_account_csv(download / ACCOUNT_SOURCE)
    tx_key = DegiroTransactionsFile.unique_key()
    acc_key = DegiroAccountFile.unique_key()

    incoming_tx_covered = _records_cover(existing_tx, incoming_tx, tx_key)
    existing_tx_covered = _records_cover(incoming_tx, existing_tx, tx_key)
    incoming_acc_covered = _records_cover(existing_acc, incoming_acc, acc_key)
    existing_acc_covered = _records_cover(incoming_acc, existing_acc, acc_key)
    portfolio_equal = _portfolio_equal(existing[PORTFOLIO_SOURCE], download / PORTFOLIO_SOURCE)

    if portfolio_equal and incoming_tx_covered and incoming_acc_covered:
        return _DECISION_SKIP

    # Ten sam {od}_{do} z Account: ledger bez nowych wierszy, Portfolio = świeższy MTM.
    if incoming_tx_covered and incoming_acc_covered:
        return _DECISION_REPLACE_PORTFOLIO

    # Incoming ma wszystkie dotychczasowe księgowania + ewentualnie więcej → podmień pakiet.
    if existing_tx_covered and existing_acc_covered:
        return _DECISION_REPLACE_PACKAGE

    return _DECISION_CONFLICT


def _replace_portfolio_only(
    download: Path,
    target_dir: Path,
    existing: dict[str, Path],
    *,
    period_start,
    period_end,
    fetched,
) -> list[MoveResult]:
    results: list[MoveResult] = []
    new_portfolio = target_dir / dated_filename(
        PORTFOLIO_PREFIX, period_start, period_end, fetched
    )
    old_portfolio = existing[PORTFOLIO_SOURCE]
    src_portfolio = download / PORTFOLIO_SOURCE
    src_portfolio.replace(new_portfolio)
    if old_portfolio.resolve() != new_portfolio.resolve() and old_portfolio.is_file():
        old_portfolio.unlink()
    results.append(
        MoveResult(
            source=src_portfolio,
            destination=new_portfolio,
            action=ACTION_MOVED,
            kind=KIND_DEGIRO,
        )
    )
    for source_name in (TRANSACTIONS_SOURCE, ACCOUNT_SOURCE):
        (download / source_name).unlink(missing_ok=True)
        results.append(
            MoveResult(
                source=download / source_name,
                destination=existing[source_name],
                action=ACTION_SKIPPED,
                kind=KIND_DEGIRO,
            )
        )
    return sorted(results, key=lambda r: r.source.name)


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
