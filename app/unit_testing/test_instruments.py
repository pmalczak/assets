# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from analyse_assets.config_model import CATALOG_SHEET, MANUAL_SHEET, RULES_SHEET
from analyse_assets.validate_config import validate_analyse_config
from importers.assets.data_model import INSTRUMENTS_SHEET, Instruments
from importers.assets.instruments import (
    InstrumentMapError,
    apply_gm_instrument_names,
    empty_instruments_table,
    instrument_map_from_frame,
    instrument_table_from_rows,
    load_instrument_map,
)
from maintenance.ensure_instruments_sheet import (
    ensure_instruments_sheet,
    upgrade_instruments_table,
)
from global_momentum.global_momentum_common import display_name
from global_momentum.global_momentum_u8_ranking import (
    POLAND_XTB_TICKER,
    RANKING_TICKERS,
    SAFE_RANKING_TICKER,
    annotate_asset_top3_drift,
)


def _rows(*items: dict) -> pd.DataFrame:
    return instrument_table_from_rows(list(items))


def _gm_mapping_rows(*, safe: str | None = None) -> list[dict]:
    rows = []
    for key, ticker in RANKING_TICKERS.items():
        rows.append(
            {
                Instruments.INSTRUMENT: f"{key} ETF",
                Instruments.DEGIRO: "",
                Instruments.XTB: POLAND_XTB_TICKER if key == "Poland" else "",
                Instruments.GM: ticker,
            }
        )
    if safe is not None:
        rows.append(
            {
                Instruments.INSTRUMENT: safe,
                Instruments.DEGIRO: "",
                Instruments.XTB: "",
                Instruments.GM: SAFE_RANKING_TICKER,
            }
        )
    return rows


class InstrumentMapTests(unittest.TestCase):
    def test_lookup_degiro_and_xtb(self):
        mapping = instrument_map_from_frame(
            _rows(
                {
                    Instruments.INSTRUMENT: "Japan IMI",
                    Instruments.DEGIRO: "IE00B4L5YX21",
                    Instruments.XTB: "",
                },
                {
                    Instruments.INSTRUMENT: "Poland ETF",
                    Instruments.DEGIRO: "",
                    Instruments.XTB: "ETFPZUW20M40.PL",
                },
            )
        )
        self.assertEqual(mapping.instrument_for_degiro("IE00B4L5YX21"), "Japan IMI")
        self.assertEqual(mapping.instrument_for_xtb("ETFPZUW20M40.PL"), "Poland ETF")

    def test_lookup_gm_and_duplicate_gm_is_error(self):
        mapping = instrument_map_from_frame(
            _rows(
                {
                    Instruments.INSTRUMENT: "Poland ETF",
                    Instruments.DEGIRO: "",
                    Instruments.XTB: POLAND_XTB_TICKER,
                    Instruments.GM: RANKING_TICKERS["Poland"],
                },
            )
        )
        self.assertEqual(mapping.instrument_for_gm(RANKING_TICKERS["Poland"]), "Poland ETF")
        with self.assertRaises(InstrumentMapError):
            instrument_map_from_frame(
                _rows(
                    {
                        Instruments.INSTRUMENT: "A",
                        Instruments.DEGIRO: "",
                        Instruments.XTB: "",
                        Instruments.GM: "SXR8.DE",
                    },
                    {
                        Instruments.INSTRUMENT: "B",
                        Instruments.DEGIRO: "",
                        Instruments.XTB: "",
                        Instruments.GM: "SXR8.DE",
                    },
                )
            )

    def test_duplicate_instrument_or_code_is_error(self):
        with self.assertRaises(InstrumentMapError):
            instrument_map_from_frame(
                _rows(
                    {Instruments.INSTRUMENT: "A", Instruments.DEGIRO: "IE00A", Instruments.XTB: ""},
                    {Instruments.INSTRUMENT: "A", Instruments.DEGIRO: "IE00B", Instruments.XTB: ""},
                )
            )
        with self.assertRaises(InstrumentMapError):
            instrument_map_from_frame(
                _rows(
                    {Instruments.INSTRUMENT: "A", Instruments.DEGIRO: "IE00A", Instruments.XTB: ""},
                    {Instruments.INSTRUMENT: "B", Instruments.DEGIRO: "IE00A", Instruments.XTB: ""},
                )
            )

    def test_require_lists_missing_codes(self):
        mapping = instrument_map_from_frame(
            _rows(
                {Instruments.INSTRUMENT: "Japan IMI", Instruments.DEGIRO: "IE00B4L5YX21", Instruments.XTB: ""},
            )
        )
        with self.assertRaises(InstrumentMapError) as ctx:
            mapping.require_degiro(["IE00B4L5YX21", "LT0000128621"])
        self.assertIn("LT0000128621", str(ctx.exception))
        self.assertNotIn("IE00B4L5YX21", str(ctx.exception).split(":")[-1])
        with self.assertRaises(InstrumentMapError) as ctx:
            mapping.require_gm(["SXR8.DE"])
        self.assertIn("SXR8.DE", str(ctx.exception))

    def test_load_requires_sheet_and_allows_extra_columns(self):
        path = Path(tempfile.mkdtemp()) / "a_config.xlsx"
        table = _rows(
            {
                Instruments.INSTRUMENT: "Japan IMI",
                Instruments.DEGIRO: "IE00B4L5YX21",
                Instruments.XTB: "",
                "coin": "later",
            }
        )
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            table.to_excel(writer, sheet_name=INSTRUMENTS_SHEET, index=False)
        mapping = load_instrument_map(path)
        self.assertEqual(mapping.instrument_for_degiro("IE00B4L5YX21"), "Japan IMI")

        empty = Path(tempfile.mkdtemp()) / "empty.xlsx"
        with pd.ExcelWriter(empty, engine="openpyxl") as writer:
            pd.DataFrame({"x": [1]}).to_excel(writer, sheet_name="assets", index=False)
        with self.assertRaises(InstrumentMapError):
            load_instrument_map(empty)


class InstrumentsValidateTests(unittest.TestCase):
    def test_validate_reports_missing_instruments_sheet(self):
        path = Path(tempfile.mkdtemp()) / "a_config.xlsx"
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            pd.DataFrame({"asset_id": ["x"]}).to_excel(writer, sheet_name=CATALOG_SHEET, index=False)
            pd.DataFrame().to_excel(writer, sheet_name=RULES_SHEET, index=False)
            pd.DataFrame().to_excel(writer, sheet_name=MANUAL_SHEET, index=False)
        report = validate_analyse_config(path)
        codes = [item.code for item in report.errors]
        self.assertIn("missing_sheet", codes)

    def test_empty_instruments_sheet_is_valid_structure(self):
        path = Path(tempfile.mkdtemp()) / "a_config.xlsx"
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            pd.DataFrame({"asset_id": ["x"]}).to_excel(writer, sheet_name=CATALOG_SHEET, index=False)
            pd.DataFrame().to_excel(writer, sheet_name=RULES_SHEET, index=False)
            pd.DataFrame().to_excel(writer, sheet_name=MANUAL_SHEET, index=False)
            empty_instruments_table().to_excel(writer, sheet_name=INSTRUMENTS_SHEET, index=False)
        report = validate_analyse_config(path)
        instrument_errors = [item for item in report.errors if item.sheet == INSTRUMENTS_SHEET]
        self.assertEqual(instrument_errors, [])

    def test_empty_instruments_table_includes_gm(self):
        self.assertIn(Instruments.GM, empty_instruments_table().columns)


class ApplyGmInstrumentNamesTests(unittest.TestCase):
    def test_relabel_keeps_drift_prefixes_and_safe_fallback(self):
        mapping = instrument_map_from_frame(_rows(*_gm_mapping_rows()))
        previous = pd.DataFrame(
            {
                "Asset": [display_name("USA"), display_name("Europe"), display_name("Japan")],
                "TOP3": [True, True, True],
            }
        )
        current = pd.DataFrame(
            {
                "Asset": [display_name("USA"), display_name("Europe"), display_name("Japan")],
                "Ticker": [
                    RANKING_TICKERS["USA"],
                    RANKING_TICKERS["Europe"],
                    RANKING_TICKERS["Japan"],
                ],
                "TOP3": [True, False, True],
            }
        )
        annotated = annotate_asset_top3_drift(current, previous)
        ranking = pd.concat(
            [
                annotated,
                pd.DataFrame(
                    [
                        {
                            "Asset": display_name(key),
                            "Ticker": ticker,
                            "TOP3": False,
                        }
                        for key, ticker in RANKING_TICKERS.items()
                        if key not in {"USA", "Europe", "Japan"}
                    ]
                ),
            ],
            ignore_index=True,
        )
        allocation = pd.DataFrame(
            [
                {
                    "Asset": display_name("USA"),
                    "Ticker": RANKING_TICKERS["USA"],
                    "Weight": 1 / 3,
                },
                {
                    "Asset": display_name("Safe"),
                    "Ticker": SAFE_RANKING_TICKER,
                    "Weight": 2 / 3,
                },
            ]
        )
        out = apply_gm_instrument_names(
            {"ranking": ranking, "allocation": allocation},
            mapping,
        )
        assets = list(out["ranking"]["Asset"])
        self.assertIn("* USA ETF", assets)
        self.assertIn("- Europe ETF", assets)
        self.assertEqual(out["allocation"]["Asset"].iloc[0], "USA ETF")
        self.assertEqual(out["allocation"]["Asset"].iloc[-1], display_name("Safe"))
        self.assertEqual(list(out["ranking"]["Ticker"]), list(ranking["Ticker"]))

    def test_safe_uses_instruments_when_mapped(self):
        mapping = instrument_map_from_frame(_rows(*_gm_mapping_rows(safe="Cash ETF")))
        allocation = pd.DataFrame(
            [
                {
                    "Asset": display_name("Safe"),
                    "Ticker": SAFE_RANKING_TICKER,
                    "Weight": 1.0,
                }
            ]
        )
        out = apply_gm_instrument_names({"allocation": allocation}, mapping)
        self.assertEqual(out["allocation"]["Asset"].iloc[0], "Cash ETF")

    def test_missing_ranking_ticker_is_hard_error(self):
        rows = [row for row in _gm_mapping_rows() if row[Instruments.GM] != RANKING_TICKERS["USA"]]
        mapping = instrument_map_from_frame(_rows(*rows))
        with self.assertRaises(InstrumentMapError) as ctx:
            apply_gm_instrument_names({"ranking": pd.DataFrame()}, mapping)
        self.assertIn("SXR8.DE", str(ctx.exception))


class EnsureInstrumentsSheetTests(unittest.TestCase):
    def _workbook(self, **sheets: pd.DataFrame) -> Path:
        path = Path(tempfile.mkdtemp()) / "a_config.xlsx"
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            pd.DataFrame({"x": [1]}).to_excel(writer, sheet_name="assets", index=False)
            for name, frame in sheets.items():
                frame.to_excel(writer, sheet_name=name, index=False)
        return path

    def test_creates_sheet_seeded_with_ranking_tickers(self):
        path = self._workbook()
        message = ensure_instruments_sheet(path, dry_run=False, seed=False)
        self.assertIn("dodano", message)
        table = pd.read_excel(path, sheet_name=INSTRUMENTS_SHEET)
        self.assertIn(Instruments.GM, table.columns)
        gm_codes = set(table[Instruments.GM].fillna("").astype(str))
        self.assertTrue(set(RANKING_TICKERS.values()) <= gm_codes)

    def test_upgrades_existing_sheet_without_overwriting_gm(self):
        existing = pd.DataFrame(
            [
                {
                    Instruments.INSTRUMENT: "Poland ETF",
                    Instruments.DEGIRO: "",
                    Instruments.XTB: POLAND_XTB_TICKER,
                },
                {
                    Instruments.INSTRUMENT: "USA custom",
                    Instruments.DEGIRO: "",
                    Instruments.XTB: "",
                    Instruments.GM: RANKING_TICKERS["USA"],
                },
            ]
        )
        path = self._workbook(**{INSTRUMENTS_SHEET: existing})
        message = ensure_instruments_sheet(path, dry_run=False, seed=False)
        self.assertIn("zaktualizowano", message)
        table = pd.read_excel(path, sheet_name=INSTRUMENTS_SHEET)
        poland = table.loc[table[Instruments.XTB].fillna("").eq(POLAND_XTB_TICKER)].iloc[0]
        self.assertEqual(str(poland[Instruments.GM]), RANKING_TICKERS["Poland"])
        usa = table.loc[table[Instruments.GM].fillna("").eq(RANKING_TICKERS["USA"])].iloc[0]
        self.assertEqual(str(usa[Instruments.INSTRUMENT]), "USA custom")
        gm_codes = set(table[Instruments.GM].fillna("").astype(str))
        self.assertTrue(set(RANKING_TICKERS.values()) <= gm_codes)
        self.assertEqual(
            len(table.loc[table[Instruments.GM].fillna("").eq(RANKING_TICKERS["Poland"])]),
            1,
        )

    def test_upgrade_adds_gm_column_to_legacy_sheet(self):
        legacy = pd.DataFrame(
            [
                {
                    Instruments.INSTRUMENT: "Poland ETF",
                    Instruments.DEGIRO: "",
                    Instruments.XTB: POLAND_XTB_TICKER,
                }
            ]
        )
        upgraded, notes = upgrade_instruments_table(legacy)
        self.assertIn("kolumna gm", notes)
        self.assertEqual(str(upgraded.iloc[0][Instruments.GM]), RANKING_TICKERS["Poland"])
        self.assertEqual(str(upgraded.iloc[0][Instruments.INSTRUMENT]), "Poland ETF")
        self.assertEqual(len(upgraded), len(RANKING_TICKERS))

    def test_upgrade_skips_when_already_current(self):
        seeded, notes = upgrade_instruments_table(empty_instruments_table())
        self.assertTrue(notes)
        again, notes_again = upgrade_instruments_table(seeded)
        self.assertEqual(notes_again, [])
        self.assertEqual(len(again), len(RANKING_TICKERS))


if __name__ == "__main__":
    unittest.main()
