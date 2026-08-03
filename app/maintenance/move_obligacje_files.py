# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

from importers.pkobp import historia_dyspozycji as historia
from maintenance.move_downloaded_results import (
    ACTION_MOVED,
    ACTION_SKIPPED,
    KIND_OBLIGACJE,
    MoveResult,
)

OBLIGACJE_ASSET_ID = "obligacjeskarbowe"

_STAN_RACHUNKU_GLOB = "StanRachunkuRejestrowego*.xls"


def move_obligacje_files(assets_root: Path, download: Path) -> list[MoveResult]:
    """Przenosi wyciągi PKO BP (obligacje skarbowe) z Downloads do assets/obligacjeskarbowe."""
    sources = _source_files(download)
    if not sources:
        return []

    target_dir = assets_root / OBLIGACJE_ASSET_ID
    target_dir.mkdir(parents=True, exist_ok=True)

    results: list[MoveResult] = []
    for src in sources:
        if src.name.lower() == historia.HISTORIA_DYSPOZYCJI_FILE.lower():
            results.append(_move_historia(src, target_dir))
        else:
            results.append(_move_stan(src, target_dir))
    return results


def _move_historia(src: Path, target_dir: Path) -> MoveResult:
    df = historia.read_historia_excel(src)
    covering = historia.find_covering_historia(target_dir, df)
    if covering is not None:
        src.unlink()
        return MoveResult(
            source=src,
            destination=covering,
            action=ACTION_SKIPPED,
            kind=KIND_OBLIGACJE,
        )

    dst = target_dir / historia.dated_historia_filename_from_df(df)
    src.replace(dst)  # nadpisanie tej samej nazwy / zawartości jest OK
    return MoveResult(
        source=src,
        destination=dst,
        action=ACTION_MOVED,
        kind=KIND_OBLIGACJE,
    )


def _move_stan(src: Path, target_dir: Path) -> MoveResult:
    dst = target_dir / src.name
    src.replace(dst)
    return MoveResult(
        source=src,
        destination=dst,
        action=ACTION_MOVED,
        kind=KIND_OBLIGACJE,
    )


def _source_files(download: Path) -> list[Path]:
    files = list(download.glob(_STAN_RACHUNKU_GLOB))
    historia_path = download / historia.HISTORIA_DYSPOZYCJI_FILE
    if historia_path.is_file():
        files.append(historia_path)
    return sorted(files, key=lambda p: p.name.lower())
