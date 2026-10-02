# -*- coding: utf-8 -*-
"""
Audyt eksportów DEGIRO w assets/p_degiro/:

1. Pliki, których okres z nazwy `{prefix}_{od}_{do}[_fetched]` zawiera się
   całkowicie w innym pliku **tego samego** prefixu (portfolio / transactions /
   account) — można usunąć (`--delete`).
2. Luki w pokryciu pozostałych okresów (po odrzuceniu zawartych).

Porównanie tylko w obrębie jednego rodzaju (account ⊄ transactions).
Równe okresy: zostaje jeden plik (kolejność nazwy). Pliki poza konwencją
nazewnictwa są pomijane.

Użycie:
  cd app
  uv run python maintenance/prune_contained_degiro.py
  uv run python maintenance/prune_contained_degiro.py --delete
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app_proc.data_root import get_online_data_root
from importers.degiro.data_model import (
    ACCOUNT_PREFIX,
    DEFAULT_DEGIRO_ASSET_ID,
    PORTFOLIO_PREFIX,
    TRANSACTIONS_PREFIX,
)
from importers.degiro.read_degiro import extract_period
from maintenance.prune_contained_statements import (
    ACTION_CONTAINED,
    ACTION_DELETED,
    ACTION_SKIPPED,
    ContainedResult,
    GapResult,
    StatementAudit,
    StatementFile,
    find_contained_in_group,
    find_gaps_in_group,
    format_gaps,
    format_results,
)

_DEGIRO_PREFIXES = (PORTFOLIO_PREFIX, TRANSACTIONS_PREFIX, ACCOUNT_PREFIX)


def get_degiro_dir(assets_root: Path | None = None) -> Path:
    root = assets_root if assets_root is not None else get_online_data_root()
    return root / DEFAULT_DEGIRO_ASSET_ID


def parse_degiro_export(path: Path) -> tuple[str, tuple[date, date]] | None:
    for prefix in _DEGIRO_PREFIXES:
        try:
            return prefix, extract_period(path, prefix)
        except ValueError:
            continue
    return None


def collect_degiro_statements(
    degiro_dir: Path,
) -> tuple[dict[str, list[StatementFile]], list[Path]]:
    by_kind: dict[str, list[StatementFile]] = {}
    skipped: list[Path] = []
    if not degiro_dir.is_dir():
        return by_kind, skipped
    for path in sorted(degiro_dir.iterdir()):
        if not path.is_file() or path.name.startswith("."):
            continue
        parsed = parse_degiro_export(path)
        if parsed is None:
            skipped.append(path)
            continue
        kind, period = parsed
        by_kind.setdefault(kind, []).append(
            StatementFile(path=path, kind=kind, start=period[0], end=period[1])
        )
    return by_kind, skipped


def find_contained_degiro(degiro_dir: Path) -> list[ContainedResult]:
    results: list[ContainedResult] = []
    by_kind, skipped = collect_degiro_statements(degiro_dir)
    for path in skipped:
        results.append(
            ContainedResult(
                path=path,
                action=ACTION_SKIPPED,
                period=None,
                covered_by=None,
                covered_by_period=None,
            )
        )
    for files in by_kind.values():
        for item, cover in find_contained_in_group(files):
            results.append(
                ContainedResult(
                    path=item.path,
                    action=ACTION_CONTAINED,
                    period=(item.start, item.end),
                    covered_by=cover.path,
                    covered_by_period=(cover.start, cover.end),
                )
            )
    return results


def find_degiro_gaps(degiro_dir: Path) -> list[GapResult]:
    results: list[GapResult] = []
    by_kind, _skipped = collect_degiro_statements(degiro_dir)
    asset_id = degiro_dir.name
    for kind, files in by_kind.items():
        for gap, before, after in find_gaps_in_group(files):
            results.append(
                GapResult(
                    asset_id=asset_id,
                    kind=kind,
                    gap=gap,
                    before=before.path,
                    after=after.path,
                    before_period=(before.start, before.end),
                    after_period=(after.start, after.end),
                )
            )
    return results


def prune_contained_degiro(
    assets_root: Path | None = None,
    *,
    delete: bool = False,
) -> list[ContainedResult]:
    degiro_dir = get_degiro_dir(assets_root)
    results = find_contained_degiro(degiro_dir)
    if not delete:
        return results

    applied: list[ContainedResult] = []
    for result in results:
        if result.action != ACTION_CONTAINED:
            applied.append(result)
            continue
        result.path.unlink()
        applied.append(
            ContainedResult(
                path=result.path,
                action=ACTION_DELETED,
                period=result.period,
                covered_by=result.covered_by,
                covered_by_period=result.covered_by_period,
            )
        )
    return applied


def audit_degiro_statements(
    assets_root: Path | None = None,
    *,
    delete: bool = False,
) -> StatementAudit:
    degiro_dir = get_degiro_dir(assets_root)
    gaps = find_degiro_gaps(degiro_dir)
    contained = prune_contained_degiro(assets_root, delete=delete)
    return StatementAudit(contained=contained, gaps=gaps)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Audyt eksportów DEGIRO w assets/p_degiro/: pliki zawarte w innych "
            "oraz luki w pokryciu okresów (per prefix)."
        ),
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Usuń zbędne (zawarte) pliki (domyślnie tylko raport)",
    )
    parser.add_argument(
        "--assets-root",
        metavar="DIR",
        type=Path,
        help="Nadpisz katalog assets/ (domyślnie Dropbox INWESTYCJE/assets)",
    )
    args = parser.parse_args()

    assets_root = args.assets_root
    if assets_root is None:
        try:
            assets_root = get_online_data_root()
        except AssertionError as exc:
            print(exc, file=sys.stderr)
            return 1
    degiro_dir = get_degiro_dir(assets_root)
    if not degiro_dir.is_dir():
        print(f"Brak katalogu DEGIRO: {degiro_dir}", file=sys.stderr)
        return 1

    audit = audit_degiro_statements(assets_root, delete=args.delete)
    if audit.contained:
        print("=== Pliki zawarte w innych ===")
        print(format_results(audit.contained, degiro_dir.parent))
        print()

    if audit.gaps:
        print("=== Luki w pokryciu ===")
        print(format_gaps(audit.gaps))
        print()

    contained = sum(1 for r in audit.contained if r.action in {ACTION_CONTAINED, ACTION_DELETED})
    skipped = sum(1 for r in audit.contained if r.action == ACTION_SKIPPED)
    mode = "usunięte" if args.delete else "do usunięcia (dry-run)"
    print(
        f"Razem: {contained} {mode}; pominięte: {skipped}; "
        f"luki: {len(audit.gaps)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
