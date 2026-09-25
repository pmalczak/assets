# -*- coding: utf-8 -*-
"""
Audyt wyciągów w cash_pool/:

1. Pliki, których okres z nazwy zawiera się całkowicie w innym pliku
   tego samego rodzaju — można usunąć (`--delete`).
2. Luki w pokryciu pozostałych okresów (np. …_200101_200228 i
   …_200315_200630 → brak dni między 28 lutego a 15 marca).

mBank:           {rachunek8}_{YYMMDD}_{YYMMDD}.csv
Revolut account: account-statement_{YYYY-MM-DD}_{YYYY-MM-DD}_…
Revolut savings: savings-statement_{YYYY-MM-DD}_{YYYY-MM-DD}_…

Porównanie tylko w obrębie katalogu aktywa i tego samego rodzaju
(account-statement ≠ savings-statement). Pliki bez dat w nazwie (UUID
depozytów) są pomijane.

Użycie:
  cd app
  uv run python maintenance/prune_contained_statements.py
  uv run python maintenance/prune_contained_statements.py --delete
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app_proc.data_root import get_cash_pool_root
from importers.period_coverage import find_coverage_gaps

ACTION_CONTAINED = "do usunięcia"
ACTION_DELETED = "usunięty"
ACTION_SKIPPED = "pominięty (brak okresu)"
ACTION_GAP = "luka"

KIND_ACCOUNT = "account-statement"
KIND_SAVINGS = "savings-statement"

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_YYMMDD = re.compile(r"^\d{6}$")
_REVOLUT_PREFIXES = {KIND_ACCOUNT, KIND_SAVINGS}


@dataclass(frozen=True)
class StatementFile:
    path: Path
    kind: str
    start: date
    end: date

    @property
    def span_days(self) -> int:
        return (self.end - self.start).days


@dataclass(frozen=True)
class ContainedResult:
    path: Path
    action: str
    period: tuple[date, date] | None
    covered_by: Path | None
    covered_by_period: tuple[date, date] | None


@dataclass(frozen=True)
class GapResult:
    asset_id: str
    kind: str
    gap: tuple[date, date]
    before: Path
    after: Path
    before_period: tuple[date, date]
    after_period: tuple[date, date]


@dataclass(frozen=True)
class StatementAudit:
    contained: list[ContainedResult]
    gaps: list[GapResult]


def parse_yymmdd(token: str) -> date:
    """YYMMDD → zawsze 20YY (domena wyciągów cash_pool)."""
    if not _YYMMDD.fullmatch(token):
        raise ValueError(token)
    return date(2000 + int(token[:2]), int(token[2:4]), int(token[4:6]))


def statement_kind(path: Path) -> str | None:
    parts = path.stem.split("_")
    if not parts:
        return None
    if parts[0] in _REVOLUT_PREFIXES:
        return parts[0]
    if len(parts) == 3 and len(parts[0]) == 8 and parts[0].isdigit():
        return f"mbank:{parts[0]}"
    return None


def parse_statement_period(path: Path) -> tuple[date, date] | None:
    parts = path.stem.split("_")
    if len(parts) < 3:
        return None

    if parts[0] in _REVOLUT_PREFIXES:
        if not (_ISO_DATE.fullmatch(parts[1]) and _ISO_DATE.fullmatch(parts[2])):
            return None
        start, end = date.fromisoformat(parts[1]), date.fromisoformat(parts[2])
        return (start, end) if start <= end else None

    if len(parts) == 3 and _YYMMDD.fullmatch(parts[1]) and _YYMMDD.fullmatch(parts[2]):
        start, end = parse_yymmdd(parts[1]), parse_yymmdd(parts[2])
        return (start, end) if start <= end else None

    return None


def _covers(outer: StatementFile, inner: StatementFile) -> bool:
    return outer.start <= inner.start and inner.end <= outer.end


def find_contained_in_group(files: list[StatementFile]) -> list[tuple[StatementFile, StatementFile]]:
    """Zwraca (zbędny, pokrywający). Przy równym okresie zostaje jeden (nazwa)."""
    if len(files) < 2:
        return []

    ordered = sorted(files, key=lambda f: (-f.span_days, f.path.name))
    kept: list[StatementFile] = []
    contained: list[tuple[StatementFile, StatementFile]] = []
    for item in ordered:
        cover = next((k for k in kept if _covers(k, item)), None)
        if cover is None:
            kept.append(item)
        else:
            contained.append((item, cover))
    return contained


def kept_in_group(files: list[StatementFile]) -> list[StatementFile]:
    contained_paths = {item.path for item, _ in find_contained_in_group(files)}
    return [f for f in files if f.path not in contained_paths]


def find_gaps_in_group(files: list[StatementFile]) -> list[tuple[tuple[date, date], StatementFile, StatementFile]]:
    """Luki między okresami plików, które zostają po odrzuceniu zawartych."""
    kept = kept_in_group(files)
    if len(kept) < 2:
        return []

    gaps = find_coverage_gaps([(f.start, f.end) for f in kept])
    found: list[tuple[tuple[date, date], StatementFile, StatementFile]] = []
    for gap_start, gap_end in gaps:
        before_end = gap_start - timedelta(days=1)
        after_start = gap_end + timedelta(days=1)
        before = max(
            (f for f in kept if f.end == before_end),
            key=lambda f: f.path.name,
        )
        after = min(
            (f for f in kept if f.start == after_start),
            key=lambda f: f.path.name,
        )
        found.append(((gap_start, gap_end), before, after))
    return found


def iter_asset_dirs(cash_pool_root: Path, asset_id: str | None = None) -> list[Path]:
    if asset_id:
        target = cash_pool_root / asset_id
        return [target] if target.is_dir() else []
    return sorted(p for p in cash_pool_root.iterdir() if p.is_dir() and not p.name.startswith("."))


def collect_statements(asset_dir: Path) -> tuple[dict[str, list[StatementFile]], list[Path]]:
    by_kind: dict[str, list[StatementFile]] = {}
    skipped: list[Path] = []
    for path in sorted(asset_dir.iterdir()):
        if not path.is_file() or path.name.startswith("."):
            continue
        kind = statement_kind(path)
        period = parse_statement_period(path)
        if kind is None or period is None:
            skipped.append(path)
            continue
        by_kind.setdefault(kind, []).append(
            StatementFile(path=path, kind=kind, start=period[0], end=period[1])
        )
    return by_kind, skipped


def find_contained_statements(
    cash_pool_root: Path,
    *,
    asset_id: str | None = None,
) -> list[ContainedResult]:
    results: list[ContainedResult] = []
    for asset_dir in iter_asset_dirs(cash_pool_root, asset_id):
        by_kind, skipped = collect_statements(asset_dir)
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


def find_statement_gaps(
    cash_pool_root: Path,
    *,
    asset_id: str | None = None,
) -> list[GapResult]:
    results: list[GapResult] = []
    for asset_dir in iter_asset_dirs(cash_pool_root, asset_id):
        by_kind, _skipped = collect_statements(asset_dir)
        for kind, files in by_kind.items():
            for gap, before, after in find_gaps_in_group(files):
                results.append(
                    GapResult(
                        asset_id=asset_dir.name,
                        kind=kind,
                        gap=gap,
                        before=before.path,
                        after=after.path,
                        before_period=(before.start, before.end),
                        after_period=(after.start, after.end),
                    )
                )
    return results


def prune_contained_statements(
    cash_pool_root: Path | None = None,
    *,
    asset_id: str | None = None,
    delete: bool = False,
) -> list[ContainedResult]:
    cash_pool_root = cash_pool_root or get_cash_pool_root()
    results = find_contained_statements(cash_pool_root, asset_id=asset_id)
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


def audit_cash_pool_statements(
    cash_pool_root: Path | None = None,
    *,
    asset_id: str | None = None,
    delete: bool = False,
) -> StatementAudit:
    cash_pool_root = cash_pool_root or get_cash_pool_root()
    gaps = find_statement_gaps(cash_pool_root, asset_id=asset_id)
    contained = prune_contained_statements(
        cash_pool_root,
        asset_id=asset_id,
        delete=delete,
    )
    return StatementAudit(contained=contained, gaps=gaps)


def _fmt_period(period: tuple[date, date] | None) -> str:
    if period is None:
        return "—"
    return f"{period[0].isoformat()}..{period[1].isoformat()}"


def format_results(results: list[ContainedResult], cash_pool_root: Path) -> str:
    lines: list[str] = []
    current_dir: str | None = None
    for result in results:
        parent = result.path.parent
        label = parent.name if parent != cash_pool_root else str(parent)
        if label != current_dir:
            current_dir = label
            lines.append(f"{label}:")
        if result.action == ACTION_SKIPPED:
            lines.append(f"  {result.action}: {result.path.name}")
            continue
        cover_name = result.covered_by.name if result.covered_by is not None else "—"
        lines.append(
            f"  {result.action}: {result.path.name}  {_fmt_period(result.period)}"
            f"  ⊂  {cover_name}  {_fmt_period(result.covered_by_period)}"
        )
    return "\n".join(lines)


def format_gaps(gaps: list[GapResult]) -> str:
    lines: list[str] = []
    current_dir: str | None = None
    for result in gaps:
        if result.asset_id != current_dir:
            current_dir = result.asset_id
            lines.append(f"{result.asset_id}:")
        lines.append(
            f"  {ACTION_GAP}: {_fmt_period(result.gap)}"
            f"  po {result.before.name}  {_fmt_period(result.before_period)}"
            f"  przed {result.after.name}  {_fmt_period(result.after_period)}"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Audyt wyciągów w cash_pool/: pliki zawarte w innych oraz luki "
            "w pokryciu okresów."
        ),
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Usuń zbędne (zawarte) pliki (domyślnie tylko raport)",
    )
    parser.add_argument(
        "--asset",
        metavar="ID",
        help="Ogranicz do jednego katalogu aktywa",
    )
    args = parser.parse_args()

    cash_pool_root = get_cash_pool_root()
    if not cash_pool_root.is_dir():
        print(f"Brak katalogu cash_pool: {cash_pool_root}", file=sys.stderr)
        return 1

    audit = audit_cash_pool_statements(
        cash_pool_root,
        asset_id=args.asset,
        delete=args.delete,
    )
    if audit.contained:
        print("=== Pliki zawarte w innych ===")
        print(format_results(audit.contained, cash_pool_root))
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
