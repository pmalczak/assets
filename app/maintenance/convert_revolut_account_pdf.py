# -*- coding: utf-8 -*-
"""
Konwersja nowego wyciągu konta Revolut (PDF) → CSV (schemat account-statement).

Staging PDF: cash_pool/p_re oraz cash_pool/g_re (owner, bez waluty).
Wynik: jeden CSV multi-Waluta obok PDF — do ręcznej weryfikacji, potem
istniejący import (`move_revolut_files` → split *_pln / *_eur).

Nie jest podpięte pod UI / move_downloaded.

Użycie:
  cd app
  uv run python maintenance/convert_revolut_account_pdf.py
  uv run python maintenance/convert_revolut_account_pdf.py --owner p_re
  uv run python maintenance/convert_revolut_account_pdf.py /path/to/file.pdf
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app_proc.data_root import get_cash_pool_root
from importers.revolut.account_statement_pdf import convert_revolut_account_statement_pdf

_OWNERS = ("p_re", "g_re")


def _staging_dirs(cash_pool: Path, owner: str | None) -> list[Path]:
    owners = (owner,) if owner else _OWNERS
    return [cash_pool / o for o in owners]


def _pdfs_in(dir_path: Path) -> list[Path]:
    if not dir_path.is_dir():
        return []
    return sorted(
        p
        for p in dir_path.glob("*.pdf")
        if "account-statement" in p.stem.lower()
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Revolut account PDF → CSV (cash_pool/p_re|g_re, bez importu)."
    )
    parser.add_argument(
        "pdf",
        nargs="*",
        type=Path,
        help="Ścieżki PDF (opcjonalnie; domyślnie skan staging p_re/g_re)",
    )
    parser.add_argument(
        "--owner",
        choices=_OWNERS,
        default=None,
        help="Tylko cash_pool/{owner} (gdy bez jawnych ścieżek PDF)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Katalog wyjściowy CSV (domyślnie obok PDF)",
    )
    args = parser.parse_args(argv)

    if args.pdf:
        pdfs = [p.resolve() for p in args.pdf]
    else:
        cash_pool = get_cash_pool_root()
        pdfs = []
        for d in _staging_dirs(cash_pool, args.owner):
            found = _pdfs_in(d)
            if not d.is_dir():
                print(f"brak katalogu staging: {d}")
            elif not found:
                print(f"brak PDF account-statement w {d}")
            pdfs.extend(found)

    if not pdfs:
        print("brak plików PDF do konwersji")
        return 1

    rc = 0
    for pdf in pdfs:
        if not pdf.is_file():
            print(f"BRAK: {pdf}")
            rc = 1
            continue
        try:
            out = convert_revolut_account_statement_pdf(pdf, out_dir=args.out_dir)
            print(f"OK  {pdf.name} → {out}")
        except Exception as exc:
            print(f"FAIL {pdf.name}: {exc}")
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
