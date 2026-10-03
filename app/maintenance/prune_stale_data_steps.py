# -*- coding: utf-8 -*-
"""
Usuwa nieaktywne wersje cache DATA_STEP:

* katalogi ``sN`` starsze niż bieżący schemat (np. ``11 portfolio_cf/.../s3`` przy ``s6``);
* całe przestarzałe produkty (np. dawne ``10 roi/`` po przeniesieniu do ``11 portfolio_cf``).

Użycie:
  cd app
  uv run python maintenance/prune_stale_data_steps.py
  uv run python maintenance/prune_stale_data_steps.py --delete
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from data_step.metadata_class import Metadata

_SCHEMA_DIR = re.compile(r"^s(\d+)$")

ACTION_STALE = "do usunięcia"
ACTION_DELETED = "usunięty"
KIND_SCHEMA = "schema"
KIND_OBSOLETE_PRODUCT = "obsolete_product"


@dataclass(frozen=True)
class StaleSchemaDir:
    path: Path
    product: str
    schema: int
    active_schema: int
    action: str
    kind: str = KIND_SCHEMA


def active_schema_products() -> dict[str, int]:
    """Produkt DATA_STEP → numer aktywnego schematu ``sN`` w ścieżce."""
    from app_proc.portfolio_cf_step import PORTFOLIO_CF_SCHEMA, PORTFOLIO_CF_STEP

    return {PORTFOLIO_CF_STEP: int(PORTFOLIO_CF_SCHEMA)}


def obsolete_data_step_products() -> tuple[str, ...]:
    from app_proc.portfolio_cf_step import OBSOLETE_DATA_STEP_PRODUCTS

    return tuple(OBSOLETE_DATA_STEP_PRODUCTS)


def find_stale_schema_dirs(data_steps_root: Path) -> list[StaleSchemaDir]:
    """Nieaktywne ``sN`` oraz całe katalogi przestarzałych produktów."""
    root = Path(data_steps_root)
    found: list[StaleSchemaDir] = []
    for product, active in sorted(active_schema_products().items()):
        product_root = root / product
        if not product_root.is_dir():
            continue
        for date_dir in sorted(product_root.iterdir()):
            if not date_dir.is_dir():
                continue
            for child in sorted(date_dir.iterdir()):
                if not child.is_dir():
                    continue
                match = _SCHEMA_DIR.fullmatch(child.name)
                if match is None:
                    continue
                schema = int(match.group(1))
                if schema == active:
                    continue
                found.append(
                    StaleSchemaDir(
                        path=child,
                        product=product,
                        schema=schema,
                        active_schema=active,
                        action=ACTION_STALE,
                        kind=KIND_SCHEMA,
                    )
                )
    for product in obsolete_data_step_products():
        product_root = root / product
        if product_root.is_dir():
            found.append(
                StaleSchemaDir(
                    path=product_root,
                    product=product,
                    schema=0,
                    active_schema=0,
                    action=ACTION_STALE,
                    kind=KIND_OBSOLETE_PRODUCT,
                )
            )
    return found


def prune_stale_data_steps(
    data_steps_root: Path | None = None,
    *,
    delete: bool = False,
) -> list[StaleSchemaDir]:
    """Dry-run albo usuń nieaktywne cache + powiązane tokeny z ``_metadata.json``."""
    if data_steps_root is None:
        from app_proc.data_steps_root import get_data_steps_root

        data_steps_root = get_data_steps_root()
    root = Path(data_steps_root)
    stale = find_stale_schema_dirs(root)
    if not delete or not stale:
        return stale

    metadata = Metadata(root)
    tokens = _metadata_tokens_under_dirs(metadata, [item.path for item in stale])
    applied: list[StaleSchemaDir] = []
    for item in stale:
        if item.path.is_dir():
            shutil.rmtree(item.path)
        if item.kind == KIND_SCHEMA:
            _remove_empty_parents(item.path.parent, stop_at=root / item.product)
        applied.append(
            StaleSchemaDir(
                path=item.path,
                product=item.product,
                schema=item.schema,
                active_schema=item.active_schema,
                action=ACTION_DELETED,
                kind=item.kind,
            )
        )
    if tokens:
        metadata.delete_many(tokens)
    _drop_data_step_ram_cache(tokens)
    return applied


def format_stale_results(results: list[StaleSchemaDir], data_steps_root: Path) -> str:
    root = Path(data_steps_root)
    lines: list[str] = []
    current_header: str | None = None
    for item in results:
        if item.kind == KIND_OBSOLETE_PRODUCT:
            header = f"{item.product}: (przestarzały produkt)"
        else:
            header = f"{item.product}: (aktywny s{item.active_schema})"
        if header != current_header:
            current_header = header
            lines.append(header)
        try:
            rel = item.path.resolve().relative_to(root.resolve())
        except ValueError:
            rel = item.path
        if item.kind == KIND_OBSOLETE_PRODUCT:
            lines.append(f"  {item.action}: {rel.as_posix()}  (całe drzewo)")
        else:
            lines.append(
                f"  {item.action}: {rel.as_posix()}  "
                f"(s{item.schema} ≠ s{item.active_schema})"
            )
    return "\n".join(lines)


def _metadata_tokens_under_dirs(metadata: Metadata, directories: list[Path]) -> list[str]:
    roots = [path.resolve() for path in directories if path]
    if not roots:
        return []
    tokens: list[str] = []
    for token in list(metadata.get_metadata().keys()):
        try:
            path = metadata.token_as_path(token).resolve()
        except Exception:
            continue
        for directory in roots:
            if path == directory or directory in path.parents:
                tokens.append(token)
                break
    return tokens


def _remove_empty_parents(start: Path, *, stop_at: Path) -> None:
    """Usuń puste katalogi od ``start`` w górę, nie powyżej ``stop_at``."""
    stop = stop_at.resolve()
    current = start
    while True:
        try:
            resolved = current.resolve()
        except OSError:
            break
        if resolved != stop and stop not in resolved.parents:
            break
        if not current.is_dir():
            break
        try:
            if any(current.iterdir()):
                break
        except OSError:
            break
        try:
            current.rmdir()
        except OSError:
            break
        if resolved == stop:
            break
        current = current.parent


def _drop_data_step_ram_cache(tokens: list[str]) -> None:
    try:
        from data_step.data_step import DATA_STEP
    except Exception:
        return
    if not getattr(DATA_STEP, "_initialised", False):
        return
    cache = getattr(DATA_STEP, "_cache", None)
    if not isinstance(cache, dict):
        return
    for token in tokens:
        cache.pop(token, None)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Usuń nieaktywne wersje cache DATA_STEP (stare sN oraz przestarzałe "
            "produkty, np. 10 roi)."
        ),
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Usuń katalogi (domyślnie tylko raport)",
    )
    parser.add_argument(
        "--data-steps",
        metavar="DIR",
        type=Path,
        help="Nadpisz katalog data_steps",
    )
    args = parser.parse_args()

    if args.data_steps is not None:
        root = args.data_steps
    else:
        from app_proc.data_steps_root import get_data_steps_root

        root = get_data_steps_root()
    if not root.is_dir():
        print(f"Brak katalogu data_steps: {root}", file=sys.stderr)
        return 1

    results = prune_stale_data_steps(root, delete=args.delete)
    if results:
        print("=== Nieaktywny cache DATA_STEP ===")
        print(format_stale_results(results, root))
        print()
    mode = "usunięte" if args.delete else "do usunięcia (dry-run)"
    print(f"Razem: {len(results)} {mode}")
    active = ", ".join(
        f"{product}=s{schema}" for product, schema in sorted(active_schema_products().items())
    )
    print(f"Aktywne schematy: {active or '(brak)'}")
    obsolete = ", ".join(obsolete_data_step_products())
    if obsolete:
        print(f"Przestarzałe produkty: {obsolete}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
