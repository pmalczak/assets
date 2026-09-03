# -*- coding: utf-8 -*-
"""
Dodaje lub aktualizuje wymagany arkusz instruments w a_config.xlsx.

- Brak arkusza: tworzy (opcjonalnie z ISIN/ticker z DATA_STEP) i zasiewa RANKING_TICKERS.
- Arkusz istnieje: dodaje pustą kolumnę gm, uzupełnia Poland .PL → .WA, dopisuje brakujące
  tickery rankingu U7. Nie nadpisuje niepustego gm.

Użycie:
  cd app
  uv run python maintenance/ensure_instruments_sheet.py
  uv run python maintenance/ensure_instruments_sheet.py --dry-run
"""
from __future__ import annotations

import argparse
# import sys
from pathlib import Path

import pandas as pd

# APP_ROOT = Path(__file__).resolve().parent.parent
# if str(APP_ROOT) not in sys.path:
#     sys.path.insert(0, str(APP_ROOT))

from importers.assets.data_model import INSTRUMENTS_SHEET, Instruments
from importers.assets.instruments import empty_instruments_table
from importers.assets.read_assets import get_assets_file
from importers.degiro.data_model import DegiroPortfolioFile, DegiroTransactionsFile
from importers.xtb.data_model import XtbCashOperationsFile, XtbOpenPositionsFile
from global_momentum.global_momentum_u8_ranking import POLAND_XTB_TICKER, RANKING_TICKERS


def _cell(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _instrument_row(
    instrument: str,
    *,
    degiro: str = "",
    xtb: str = "",
    gm: str = "",
) -> dict[str, str]:
    return {
        Instruments.INSTRUMENT: instrument,
        Instruments.DEGIRO: degiro,
        Instruments.XTB: xtb,
        Instruments.GM: gm,
    }


def _seed_from_extracts() -> pd.DataFrame:
    rows: list[dict] = []
    seen_degiro: set[str] = set()
    seen_xtb: set[str] = set()
    root = Path(__file__).resolve().parent.parent.parent / "data_steps" / "01 source"
    portfolio = root / "p_degiro-portfolio.parquet"
    transactions = root / "p_degiro-transactions.parquet"
    if portfolio.is_file():
        frame = pd.read_parquet(portfolio)
        for _, row in frame.iterrows():
            isin = _cell(row.get(DegiroPortfolioFile.ISIN))
            if not isin or isin in seen_degiro:
                continue
            seen_degiro.add(isin)
            rows.append(
                _instrument_row(
                    _cell(row.get(DegiroPortfolioFile.PRODUCT)) or isin,
                    degiro=isin,
                )
            )
    if transactions.is_file():
        frame = pd.read_parquet(transactions)
        for _, row in frame.iterrows():
            isin = _cell(row.get(DegiroTransactionsFile.ISIN))
            if not isin or isin in seen_degiro:
                continue
            seen_degiro.add(isin)
            rows.append(
                _instrument_row(
                    _cell(row.get(DegiroTransactionsFile.PRODUCT)) or isin,
                    degiro=isin,
                )
            )
    for name in ("p_xtb-open.parquet", "p_xtb-cash.parquet"):
        path = root / name
        if not path.is_file():
            continue
        frame = pd.read_parquet(path)
        ticker_col = (
            XtbOpenPositionsFile.TICKER if XtbOpenPositionsFile.TICKER in frame.columns
            else XtbCashOperationsFile.TICKER
        )
        for ticker in frame[ticker_col].map(_cell):
            if not ticker or ticker in seen_xtb:
                continue
            seen_xtb.add(ticker)
            rows.append(_instrument_row(ticker, xtb=ticker))
    if not rows:
        return empty_instruments_table()
    return pd.DataFrame(rows, columns=list(Instruments.expected_columns()))


def _ordered_instruments(table: pd.DataFrame) -> pd.DataFrame:
    preferred = [
        Instruments.INSTRUMENT,
        Instruments.DEGIRO,
        Instruments.XTB,
        Instruments.GM,
    ]
    ordered = [column for column in preferred if column in table.columns]
    extras = [column for column in table.columns if column not in ordered]
    return table[ordered + extras]


def _fill_poland_gm(table: pd.DataFrame) -> pd.DataFrame:
    work = table.copy()
    poland_gm = RANKING_TICKERS["Poland"]
    existing = {_cell(value) for value in work[Instruments.GM]}
    if poland_gm in existing or Instruments.XTB not in work.columns:
        return work
    xtb = work[Instruments.XTB].map(_cell)
    gm = work[Instruments.GM].map(_cell)
    matches = work.index[xtb.eq(POLAND_XTB_TICKER) & gm.eq("")]
    if len(matches):
        work.loc[matches[0], Instruments.GM] = poland_gm
    return work


def _append_missing_ranking_tickers(table: pd.DataFrame) -> pd.DataFrame:
    work = table.copy()
    existing = {_cell(value) for value in work[Instruments.GM]}
    extra = [
        _instrument_row(universe_key, gm=ticker)
        for universe_key, ticker in RANKING_TICKERS.items()
        if ticker not in existing
    ]
    if not extra:
        return work
    added = pd.DataFrame(extra)
    if work.empty:
        work = added
    else:
        work = pd.concat([work, added], ignore_index=True)
    return work.fillna("")


def upgrade_instruments_table(table: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Dodaj gm, uzupełnij Poland, dopisz brakujące RANKING_TICKERS. Nie ruszaj niepustego gm."""
    notes: list[str] = []
    work = table.copy()
    for column in Instruments.expected_columns():
        if column not in work.columns:
            work[column] = ""
            notes.append(f"kolumna {column}")
    for column in Instruments.expected_columns():
        work[column] = work[column].map(_cell)

    before_poland = work[Instruments.GM].map(_cell)
    work = _fill_poland_gm(work)
    if list(work[Instruments.GM].map(_cell)) != list(before_poland):
        notes.append(f"Poland gm={RANKING_TICKERS['Poland']}")

    n_before = len(work)
    work = _append_missing_ranking_tickers(work)
    added = len(work) - n_before
    if added:
        notes.append(f"{added} wiersz(y) RANKING_TICKERS")
    return _ordered_instruments(work), notes


def _write_instruments_sheet(config_path: Path, table: pd.DataFrame) -> None:
    with pd.ExcelWriter(
        config_path,
        engine="openpyxl",
        mode="a",
        if_sheet_exists="replace",
    ) as writer:
        table.to_excel(writer, sheet_name=INSTRUMENTS_SHEET, index=False)


def ensure_instruments_sheet(config_path: Path, *, dry_run: bool, seed: bool) -> str:
    with pd.ExcelFile(config_path) as xf:
        names = set(xf.sheet_names)
    if INSTRUMENTS_SHEET not in names:
        table = _seed_from_extracts() if seed else empty_instruments_table()
        upgraded, notes = upgrade_instruments_table(table)
        detail = ", ".join(notes) if notes else f"{len(upgraded)} wierszy"
        if dry_run:
            return (
                f"DRY-RUN: dodałbym {INSTRUMENTS_SHEET!r} "
                f"({len(upgraded)} wierszy; {detail}) do {config_path}"
            )
        _write_instruments_sheet(config_path, upgraded)
        return (
            f"OK: dodano {INSTRUMENTS_SHEET!r} "
            f"({len(upgraded)} wierszy) do {config_path}"
        )

    original = pd.read_excel(config_path, sheet_name=INSTRUMENTS_SHEET)
    upgraded, notes = upgrade_instruments_table(original)
    if not notes:
        return f"OK: arkusz {INSTRUMENTS_SHEET!r} już jest aktualny w {config_path}"
    detail = ", ".join(notes)
    if dry_run:
        return (
            f"DRY-RUN: zaktualizowałbym {INSTRUMENTS_SHEET!r} ({detail}) w {config_path}"
        )
    _write_instruments_sheet(config_path, upgraded)
    return f"OK: zaktualizowano {INSTRUMENTS_SHEET!r} ({detail}) w {config_path}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--no-seed",
        action="store_true",
        help="Bez ISIN/ticker z wyciągów; RANKING_TICKERS i tak są zasiewane",
    )
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args(argv)
    path = args.config or get_assets_file()
    print(ensure_instruments_sheet(path, dry_run=args.dry_run, seed=not args.no_seed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
