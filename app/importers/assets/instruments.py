# -*- coding: utf-8 -*-
"""Kanoniczne nazwy instrumentów z a_config.xlsx (arkusz instruments)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from importers.assets.data_model import INSTRUMENTS_SHEET, Instruments
from importers.assets.read_assets import get_assets_file

SAFE_GM_TICKERS = ("EXVM.DE", "ETFBCASH.PL")


class InstrumentMapError(ValueError):
    """Brak lub niepoprawny arkusz instruments."""


def _cell(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if text.lower() == "nan":
        return ""
    return text


def empty_instruments_table() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[Instruments.INSTRUMENT, Instruments.DEGIRO, Instruments.XTB, Instruments.GM]
    )


def instrument_table_from_rows(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    for column in Instruments.expected_columns():
        if column not in frame.columns:
            frame[column] = ""
    ordered = list(Instruments.expected_columns()) + [
        column for column in frame.columns if column not in Instruments.expected_columns()
    ]
    return frame[ordered]


@dataclass(frozen=True)
class InstrumentMap:
    table: pd.DataFrame
    _by_degiro: dict[str, str]
    _by_xtb: dict[str, str]
    _by_gm: dict[str, str]

    def instrument_for_degiro(self, isin: str) -> str:
        return self._lookup("ISIN DEGIRO", self._by_degiro, isin)

    def instrument_for_xtb(self, ticker: str) -> str:
        return self._lookup("ticker XTB", self._by_xtb, ticker)

    def instrument_for_gm(self, ticker: str) -> str:
        return self._lookup("ticker GM", self._by_gm, ticker)

    def _lookup(self, label: str, index: dict[str, str], key: str) -> str:
        code = _cell(key)
        if not code:
            raise InstrumentMapError(f"Pusty {label} — nie ma wiersza w instruments.")
        name = index.get(code)
        if name is None:
            raise InstrumentMapError(
                f"{label} {code!r} nie ma wiersza w arkuszu {INSTRUMENTS_SHEET!r}."
            )
        return name

    def require_degiro(self, isins: list[str] | set[str]) -> None:
        self._require("DEGIRO", "degiro = ISIN z wyciągu", self._by_degiro, isins)

    def require_xtb(self, tickers: list[str] | set[str]) -> None:
        self._require("XTB", "xtb = ticker z wyciągu", self._by_xtb, tickers)

    def require_gm(self, tickers: list[str] | set[str]) -> None:
        self._require("GM", "gm = ticker Yahoo z rankingu U7", self._by_gm, tickers)

    def _require(
        self,
        venue: str,
        hint: str,
        index: dict[str, str],
        codes: list[str] | set[str],
    ) -> None:
        missing = sorted({_cell(code) for code in codes if _cell(code)} - set(index))
        if missing:
            listed = ", ".join(missing)
            raise InstrumentMapError(
                f"Brak mapowania {venue} w arkuszu {INSTRUMENTS_SHEET!r}: {listed}. "
                f"Dopisz wiersze (kolumna {hint})."
            )

    def instrument_for_safe(self) -> str | None:
        for ticker in SAFE_GM_TICKERS:
            name = self._by_gm.get(ticker)
            if name:
                return name
        return None


def instrument_map_from_frame(table: pd.DataFrame, *, source: str = "memory") -> InstrumentMap:
    Instruments.check_structure(table, file=source)
    work = table.copy()
    work[Instruments.INSTRUMENT] = work[Instruments.INSTRUMENT].map(_cell)
    work[Instruments.DEGIRO] = work[Instruments.DEGIRO].map(_cell)
    work[Instruments.XTB] = work[Instruments.XTB].map(_cell)
    work[Instruments.GM] = work[Instruments.GM].map(_cell)
    work = work.loc[work[Instruments.INSTRUMENT].ne("")].copy()

    names = work[Instruments.INSTRUMENT].tolist()
    dup_names = sorted({name for name in names if names.count(name) > 1})
    if dup_names:
        raise InstrumentMapError(
            f"Zduplikowana nazwa instrumentu w {INSTRUMENTS_SHEET!r}: {', '.join(dup_names)}"
        )

    by_degiro: dict[str, str] = {}
    by_xtb: dict[str, str] = {}
    by_gm: dict[str, str] = {}
    for _, row in work.iterrows():
        name = row[Instruments.INSTRUMENT]
        _index_unique(by_degiro, row[Instruments.DEGIRO], name, "ISIN DEGIRO")
        _index_unique(by_xtb, row[Instruments.XTB], name, "ticker XTB")
        _index_unique(by_gm, row[Instruments.GM], name, "ticker GM")
    return InstrumentMap(table=work, _by_degiro=by_degiro, _by_xtb=by_xtb, _by_gm=by_gm)


def _index_unique(index: dict[str, str], code: str, name: str, label: str) -> None:
    if not code:
        return
    if code in index:
        raise InstrumentMapError(
            f"Zduplikowany {label} {code!r} w {INSTRUMENTS_SHEET!r} "
            f"({index[code]!r} i {name!r})"
        )
    index[code] = name


def load_instrument_map(config_path: Path | None = None) -> InstrumentMap:
    source = config_path if config_path is not None else get_assets_file()
    if not source.is_file():
        raise InstrumentMapError(f"Brak pliku konfiguracji: {source}")
    with pd.ExcelFile(source) as xf:
        names = set(xf.sheet_names)
    if INSTRUMENTS_SHEET not in names:
        raise InstrumentMapError(
            f"Brak wymaganego arkusza {INSTRUMENTS_SHEET!r} w {source}. "
            "Klucz = instrument (nazwa pokazywana w aplikacji); "
            "kolumny degiro (ISIN), xtb (ticker), gm (ticker Yahoo U7)."
        )
    table = pd.read_excel(source, sheet_name=INSTRUMENTS_SHEET)
    return instrument_map_from_frame(table, source=str(source))


def apply_gm_instrument_names(result: dict, mapping: InstrumentMap) -> dict:
    """Podmień kolumnę Asset w tabelach rankingu U7 na instruments.instrument."""
    from global_momentum.global_momentum_u8_ranking import RANKING_TICKERS

    mapping.require_gm(RANKING_TICKERS.values())
    out = dict(result)
    for key in ("ranking", "allocation", "availability"):
        frame = out.get(key)
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            out[key] = _relabel_gm_asset_column(frame, mapping)
    return out


def _relabel_gm_asset_column(frame: pd.DataFrame, mapping: InstrumentMap) -> pd.DataFrame:
    work = frame.copy()
    if "Ticker" not in work.columns or "Asset" not in work.columns:
        return work
    renamed: list[str] = []
    for asset, ticker in zip(work["Asset"].astype(str), work["Ticker"].map(_cell)):
        if not ticker:
            renamed.append(asset)
            continue
        try:
            name = mapping.instrument_for_gm(ticker)
        except InstrumentMapError:
            if ticker not in SAFE_GM_TICKERS:
                raise
            name = mapping.instrument_for_safe()
            if name is None:
                renamed.append(asset)
                continue
        renamed.append(_with_drift_prefix(asset, name))
    work["Asset"] = renamed
    return work


def _with_drift_prefix(original: str, name: str) -> str:
    text = str(original or "")
    for marker in ("* ", "+ ", "- "):
        if text.startswith(marker):
            return f"{marker}{name}"
    if text[:1] in "*+-" and len(text) > 1:
        return f"{text[:1]} {name}"
    return name
