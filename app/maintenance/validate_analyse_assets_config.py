# -*- coding: utf-8 -*-
"""
Waliduje arkusze ROI w a_config.xlsx względem schematu i procedur.

Akceptuje wyłącznie nową strukturę (AccountTx / pool_id).
Aliasy wsteczne (MBANK_*, SOURCE, kolumna source) są błędami.

Użycie:
  cd app
  uv run python maintenance/validate_analyse_assets_config.py
  uv run python maintenance/validate_analyse_assets_config.py C:/sciezka/a_config.xlsx
  uv run python maintenance/validate_analyse_assets_config.py --with-pool
"""
from __future__ import annotations

import argparse
from pathlib import Path

from analyse_assets.validate_config import print_report, validate_analyse_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Walidacja arkuszy ROI w a_config.xlsx",
    )
    parser.add_argument(
        "config_path",
        nargs="?",
        type=Path,
        default=None,
        help="Ścieżka do xlsx (domyślnie Dropbox/INWESTYCJE/assets/a_config.xlsx)",
    )
    parser.add_argument(
        "--with-pool",
        action="store_true",
        help="Dodatkowo uruchom selektory względem poola mbank_pln",
    )
    args = parser.parse_args(argv)

    report = validate_analyse_config(
        args.config_path,
        check_pool=args.with_pool,
    )
    print_report(report)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
