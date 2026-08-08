# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from importers.traderepublic.data_model import (
    DEFAULT_TRADEREPUBLIC_ASSET_ID,
    SOURCE_EXPORT_STEM,
    TradeRepublicFile,
)
from importers.traderepublic.read_traderepublic import (
    dated_export_filename,
    is_traderepublic_export_header,
    period_from_dataframe,
)
from maintenance.move_downloaded_results import (
    ACTION_DELETED_EMPTY,
    ACTION_MOVED,
    ACTION_SKIPPED,
    KIND_TRADEREPUBLIC,
    MoveResult,
)

DOWNLOAD_PM = Path("Dropbox/INWESTYCJE/download/pm")


def move_traderepublic_files(assets_root: Path, download_dir: Path | None = None) -> list[MoveResult]:
    """Przenosi `Eksport transakcji.csv` z download/pm → assets/p_traderepublic/."""
    download = download_dir or (Path.home() / DOWNLOAD_PM)
    if not download.is_dir():
        return []

    results: list[MoveResult] = []
    for src in sorted(download.glob("*.csv")):
        if src.stem != SOURCE_EXPORT_STEM:
            continue
        results.append(_move_export(src, assets_root))
    return results


def _move_export(src: Path, assets_root: Path) -> MoveResult:
    df = pd.read_csv(src)
    if df.empty:
        src.unlink()
        return MoveResult(
            source=src,
            destination=None,
            action=ACTION_DELETED_EMPTY,
            kind=KIND_TRADEREPUBLIC,
        )
    if not is_traderepublic_export_header(df.columns):
        # Nie nasz pełny eksport TR — zostaw w inboxie (Revolut też pominie).
        return MoveResult(
            source=src,
            destination=None,
            action=ACTION_SKIPPED,
            kind=KIND_TRADEREPUBLIC,
        )

    period_start, period_end = period_from_dataframe(df)
    target_dir = assets_root / DEFAULT_TRADEREPUBLIC_ASSET_ID
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / dated_export_filename(period_start, period_end)

    if target.is_file():
        existing = pd.read_csv(target)
        decision = _resolve_existing_target(existing, df)
        if decision == "skip":
            src.unlink()
            return MoveResult(
                source=src,
                destination=target,
                action=ACTION_SKIPPED,
                kind=KIND_TRADEREPUBLIC,
            )
        if decision == "conflict":
            raise ValueError(
                f"Konflikt treści Trade Republic dla okresu "
                f"{period_start.isoformat()}..{period_end.isoformat()}: "
                f"{target.name} vs {src.name}"
            )

    src.replace(target)
    return MoveResult(
        source=src,
        destination=target,
        action=ACTION_MOVED,
        kind=KIND_TRADEREPUBLIC,
    )


def _resolve_existing_target(existing: pd.DataFrame, incoming: pd.DataFrame) -> str:
    """
    skip — istniejący już zawiera wszystkie transaction_id z incoming;
    overwrite — incoming jest nadzbiorem (lub równy po ID) bez konfliktów wierszy;
    conflict — te same ID, różne dane.
    """
    id_col = TradeRepublicFile.TRANSACTION_ID
    if id_col not in existing.columns or id_col not in incoming.columns:
        return "conflict"

    old_ids = set(existing[id_col].astype(str))
    new_ids = set(incoming[id_col].astype(str))
    common = old_ids & new_ids
    if common:
        old_by_id = existing.set_index(existing[id_col].astype(str), drop=False)
        new_by_id = incoming.set_index(incoming[id_col].astype(str), drop=False)
        for tx_id in common:
            old_row = old_by_id.loc[tx_id]
            new_row = new_by_id.loc[tx_id]
            if isinstance(old_row, pd.DataFrame):
                old_row = old_row.iloc[0]
            if isinstance(new_row, pd.DataFrame):
                new_row = new_row.iloc[0]
            if not _rows_equal(old_row, new_row):
                return "conflict"

    if new_ids <= old_ids:
        return "skip"
    return "overwrite"


def _rows_equal(a: pd.Series, b: pd.Series) -> bool:
    cols = [c for c in REQUIRED_COMPARE_COLUMNS if c in a.index and c in b.index]
    for col in cols:
        av, bv = a[col], b[col]
        if pd.isna(av) and pd.isna(bv):
            continue
        if str(av) != str(bv):
            return False
    return True


REQUIRED_COMPARE_COLUMNS = (
    TradeRepublicFile.DATETIME,
    TradeRepublicFile.DATE,
    TradeRepublicFile.TYPE,
    TradeRepublicFile.AMOUNT,
    TradeRepublicFile.CURRENCY,
    TradeRepublicFile.TRANSACTION_ID,
    TradeRepublicFile.DESCRIPTION,
)
