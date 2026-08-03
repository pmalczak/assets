# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from evaluators.evaluate_broker_obligacje import evaluate_broker_obligacje, is_obligacje_broker
from importers.assets.data_model import AssetsDef, GroupDomain, KindDomain, TypeDomain
from importers.pkobp.data_model import PkoBpBonds, PkoBpStan, is_cashflow_register
from importers.pkobp.read_historia import (
    _append_manual_cashflows,
    _negate_paper_sell_qty,
    _normalize_cashflow_amounts,
    filter_cashflow_register,
    open_qty_by_code,
)
from importers.pkobp.read_stan import add_unit_price, select_stan_as_of, stan_mtm_total
from roi.broker_obligacje_roi import build_bonds_cashflows, compute_bonds_broker_roi_from_frames
from roi.categories import CAPEX, DIVESTMENT
from roi.data_model import CashFlowEvent


def _catalog_row() -> pd.Series:
    return pd.Series(
        {
            AssetsDef.ID: "obligacjeskarbowe",
            AssetsDef.KIND: KindDomain.BROKER,
            AssetsDef.TYPE: TypeDomain.BONDS,
            AssetsDef.GROUP: GroupDomain.INVESTMENT,
            AssetsDef.CURRENCY: "PLN",
            AssetsDef.DESCR: "obligacje",
            AssetsDef.NOTES: "",
        }
    )


def _historia_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                PkoBpBonds.DATE: date(2024, 1, 10),
                PkoBpBonds.ORDER_TYPE: "dyspozycja zakupu",
                PkoBpBonds.CODE: "EDO1029",
                PkoBpBonds.NO_LINE: 1,
                PkoBpBonds.SERIES: "A",
                PkoBpBonds.BONDS_NO: 500,
                PkoBpBonds.AMOUNT: 50000.0,
                PkoBpBonds.STAT: "zrealizowana",
                PkoBpBonds.NOTES: "",
            },
            {
                PkoBpBonds.DATE: date(2024, 1, 10),
                PkoBpBonds.ORDER_TYPE: "zakup papierów",
                PkoBpBonds.CODE: "EDO1029",
                PkoBpBonds.NO_LINE: 1,
                PkoBpBonds.SERIES: "A",
                PkoBpBonds.BONDS_NO: 500,
                PkoBpBonds.AMOUNT: -50000.0,  # po normalizacji 01 source
                PkoBpBonds.STAT: "zrealizowana",
                PkoBpBonds.NOTES: "",
            },
            {
                PkoBpBonds.DATE: date(2024, 6, 1),
                PkoBpBonds.ORDER_TYPE: "naliczenie odsetek na 2024-06-01",
                PkoBpBonds.CODE: "EDO1029",
                PkoBpBonds.NO_LINE: 2,
                PkoBpBonds.SERIES: "A",
                PkoBpBonds.BONDS_NO: 0,
                PkoBpBonds.AMOUNT: -1200.0,  # REVENUES — po normalizacji 01 source
                PkoBpBonds.STAT: "zrealizowana",
                PkoBpBonds.NOTES: "",
            },
            {
                PkoBpBonds.DATE: date(2024, 6, 2),
                PkoBpBonds.ORDER_TYPE: "podatek",
                PkoBpBonds.CODE: "EDO1029",
                PkoBpBonds.NO_LINE: 3,
                PkoBpBonds.SERIES: "A",
                PkoBpBonds.BONDS_NO: 0,
                PkoBpBonds.AMOUNT: 200.0,  # OPEX — po normalizacji 01 source
                PkoBpBonds.STAT: "zrealizowana",
                PkoBpBonds.NOTES: "",
            },
            {
                PkoBpBonds.DATE: date(2023, 1, 1),
                PkoBpBonds.ORDER_TYPE: "dyspozycja zakupu",
                PkoBpBonds.CODE: "COI0723",
                PkoBpBonds.NO_LINE: 4,
                PkoBpBonds.SERIES: "A",
                PkoBpBonds.BONDS_NO: 100,
                PkoBpBonds.AMOUNT: 10000.0,
                PkoBpBonds.STAT: "zrealizowana",
                PkoBpBonds.NOTES: "",
            },
            {
                PkoBpBonds.DATE: date(2023, 1, 1),
                PkoBpBonds.ORDER_TYPE: "zakup papierów",
                PkoBpBonds.CODE: "COI0723",
                PkoBpBonds.NO_LINE: 4,
                PkoBpBonds.SERIES: "A",
                PkoBpBonds.BONDS_NO: 100,
                PkoBpBonds.AMOUNT: -10000.0,  # po normalizacji 01 source
                PkoBpBonds.STAT: "zrealizowana",
                PkoBpBonds.NOTES: "",
            },
            {
                PkoBpBonds.DATE: date(2023, 8, 1),
                PkoBpBonds.ORDER_TYPE: "wykup papierów",
                PkoBpBonds.CODE: "COI0723",
                PkoBpBonds.NO_LINE: 5,
                PkoBpBonds.SERIES: "A",
                PkoBpBonds.BONDS_NO: 100,
                PkoBpBonds.AMOUNT: None,
                PkoBpBonds.STAT: "zrealizowana",
                PkoBpBonds.NOTES: "",
            },
            {
                PkoBpBonds.DATE: date(2023, 8, 1),
                PkoBpBonds.ORDER_TYPE: "wypłata przelewem",
                PkoBpBonds.CODE: "COI0723",
                PkoBpBonds.NO_LINE: 0,
                PkoBpBonds.SERIES: "A",
                PkoBpBonds.BONDS_NO: 0,
                PkoBpBonds.AMOUNT: 10500.0,  # DIVESTMENT — po normalizacji 01 source
                PkoBpBonds.STAT: "zrealizowana",
                PkoBpBonds.NOTES: "",
            },
            {
                PkoBpBonds.DATE: date(2023, 8, 1),
                PkoBpBonds.ORDER_TYPE: "wykup - odsetki",
                PkoBpBonds.CODE: "COI0723",
                PkoBpBonds.NO_LINE: 5,
                PkoBpBonds.SERIES: "A",
                PkoBpBonds.BONDS_NO: 0,
                PkoBpBonds.AMOUNT: -500.0,  # REVENUES — po normalizacji 01 source
                PkoBpBonds.STAT: "zrealizowana",
                PkoBpBonds.NOTES: "",
            },
        ]
    )


def _stan_df() -> pd.DataFrame:
    raw = pd.DataFrame(
        [
            {
                PkoBpStan.EMISSION: "EDO1029",
                PkoBpStan.QTY_AVAILABLE: 500,
                PkoBpStan.QTY_BLOCKED: 0,
                PkoBpStan.NOMINAL: 50000,
                PkoBpStan.CURRENT_VALUE: 82550,
                PkoBpStan.MATURITY: date(2029, 10, 5),
                PkoBpStan.FILE_DATE: "2026-08-03",
            },
            {
                PkoBpStan.EMISSION: "EDO1029",
                PkoBpStan.QTY_AVAILABLE: 500,
                PkoBpStan.QTY_BLOCKED: 0,
                PkoBpStan.NOMINAL: 50000,
                PkoBpStan.CURRENT_VALUE: 80000,
                PkoBpStan.MATURITY: date(2029, 10, 5),
                PkoBpStan.FILE_DATE: "2026-07-23",
            },
        ]
    )
    return add_unit_price(raw)


class StanHelpersTests(unittest.TestCase):
    def test_unit_price_and_select_latest(self):
        stan = _stan_df()
        self.assertAlmostEqual(
            float(stan.loc[stan[PkoBpStan.FILE_DATE] == "2026-08-03", PkoBpStan.UNIT_PRICE].iloc[0]),
            165.1,
        )
        selected = select_stan_as_of(stan, date(2026, 8, 1))
        self.assertEqual(selected[PkoBpStan.FILE_DATE].iloc[0], "2026-07-23")
        self.assertEqual(stan_mtm_total(selected), 80000.0)
        selected2 = select_stan_as_of(stan, date(2026, 8, 3))
        self.assertEqual(stan_mtm_total(selected2), 82550.0)


class HistoriaInventoryTests(unittest.TestCase):
    def test_open_qty_uses_paper_register_not_zakup_papierow(self):
        qty = open_qty_by_code(_historia_rows(), date(2026, 8, 3))
        self.assertEqual(qty["EDO1029"], 500.0)
        self.assertEqual(qty["COI0723"], 0.0)


class BondsCashflowTests(unittest.TestCase):
    def test_only_cashflow_register(self):
        self.assertTrue(is_cashflow_register("zakup papierów"))
        self.assertTrue(is_cashflow_register("naliczenie odsetek na 2024-06-01"))
        self.assertTrue(is_cashflow_register("podatek"))
        self.assertTrue(is_cashflow_register("wypłata przelewem"))
        self.assertTrue(is_cashflow_register("odsetki"))
        self.assertTrue(is_cashflow_register("opłata za przedterminowy wykup"))
        self.assertTrue(is_cashflow_register("wykup - odsetki"))
        self.assertFalse(is_cashflow_register("wykup papierów"))
        self.assertFalse(is_cashflow_register("dyspozycja zakupu"))
        self.assertFalse(is_cashflow_register("przedterminowy wykup"))

        cash = filter_cashflow_register(_historia_rows())
        types = set(cash[PkoBpBonds.ORDER_TYPE])
        self.assertEqual(
            types,
            {
                "zakup papierów",
                "naliczenie odsetek na 2024-06-01",
                "podatek",
                "wypłata przelewem",
                "wykup - odsetki",
            },
        )

    def test_roi_mapping_only_true_cashflows(self):
        events = build_bonds_cashflows(_historia_rows(), "obligacjeskarbowe")
        df = events["obligacjeskarbowe:EDO1029"]
        self.assertEqual(df[CashFlowEvent.CATEGORY].tolist(), [CAPEX])
        self.assertAlmostEqual(float(df.iloc[0][CashFlowEvent.AMOUNT]), -50000.0)
        # naliczenie / podatek — ekonomiczne, poza ROI
        self.assertNotIn("naliczenie odsetek na 2024-06-01", df[CashFlowEvent.DESCRIPTION].tolist())

        sold = events["obligacjeskarbowe:COI0723"]
        by_desc = {
            str(r[CashFlowEvent.DESCRIPTION]): r
            for _, r in sold.iterrows()
        }
        self.assertEqual(set(by_desc), {"zakup papierów", "wypłata przelewem"})
        self.assertEqual(by_desc["zakup papierów"][CashFlowEvent.CATEGORY], CAPEX)
        self.assertEqual(by_desc["wypłata przelewem"][CashFlowEvent.CATEGORY], DIVESTMENT)
        self.assertAlmostEqual(float(by_desc["wypłata przelewem"][CashFlowEvent.AMOUNT]), 10500.0)
        self.assertNotIn("wykup - odsetki", by_desc)

    def test_import_negates_paper_sell_qty_and_adds_manual(self):
        raw = pd.DataFrame(
            [
                {
                    PkoBpBonds.DATE: "2019-10-15",
                    PkoBpBonds.ORDER_TYPE: "dyspozycja przedterminowego wykupu",
                    PkoBpBonds.CODE: "DOS1021",
                    PkoBpBonds.NO_LINE: 0,
                    PkoBpBonds.SERIES: 5,
                    PkoBpBonds.BONDS_NO: 400,
                    PkoBpBonds.AMOUNT: 0.0,
                    PkoBpBonds.STAT: "zrealizowana",
                    PkoBpBonds.NOTES: "",
                }
            ]
        )
        signed = _negate_paper_sell_qty(raw)
        self.assertEqual(float(signed.iloc[0][PkoBpBonds.BONDS_NO]), -400.0)

        with_manual = _append_manual_cashflows(pd.DataFrame(columns=list(PkoBpBonds.expected_columns())))
        self.assertEqual(len(with_manual), 2)
        self.assertTrue((with_manual[PkoBpBonds.ORDER_TYPE] == "wypłata przelewem").all())

    def test_normalize_cashflow_amounts_at_import(self):
        raw = pd.DataFrame(
            [
                {
                    PkoBpBonds.DATE: "2020-01-01",
                    PkoBpBonds.ORDER_TYPE: "zakup papierów",
                    PkoBpBonds.CODE: "X",
                    PkoBpBonds.NO_LINE: 1,
                    PkoBpBonds.SERIES: "A",
                    PkoBpBonds.BONDS_NO: 1,
                    PkoBpBonds.AMOUNT: 1000.0,
                    PkoBpBonds.STAT: "zrealizowana",
                    PkoBpBonds.NOTES: "",
                },
                {
                    PkoBpBonds.DATE: "2020-02-01",
                    PkoBpBonds.ORDER_TYPE: "naliczenie odsetek na 2020-02-01",
                    PkoBpBonds.CODE: "X",
                    PkoBpBonds.NO_LINE: 0,
                    PkoBpBonds.SERIES: "A",
                    PkoBpBonds.BONDS_NO: 0,
                    PkoBpBonds.AMOUNT: -50.0,
                    PkoBpBonds.STAT: "zrealizowana",
                    PkoBpBonds.NOTES: "",
                },
                {
                    PkoBpBonds.DATE: "2020-03-01",
                    PkoBpBonds.ORDER_TYPE: "wypłata przelewem",
                    PkoBpBonds.CODE: "X",
                    PkoBpBonds.NO_LINE: 0,
                    PkoBpBonds.SERIES: "A",
                    PkoBpBonds.BONDS_NO: 0,
                    PkoBpBonds.AMOUNT: 200.0,
                    PkoBpBonds.STAT: "zrealizowana",
                    PkoBpBonds.NOTES: "",
                },
                {
                    PkoBpBonds.DATE: "2020-03-02",
                    PkoBpBonds.ORDER_TYPE: "podatek",
                    PkoBpBonds.CODE: "X",
                    PkoBpBonds.NO_LINE: 0,
                    PkoBpBonds.SERIES: "A",
                    PkoBpBonds.BONDS_NO: 0,
                    PkoBpBonds.AMOUNT: 10.0,
                    PkoBpBonds.STAT: "zrealizowana",
                    PkoBpBonds.NOTES: "",
                },
            ]
        )
        norm = _normalize_cashflow_amounts(raw)
        by_type = {
            str(r[PkoBpBonds.ORDER_TYPE]): float(r[PkoBpBonds.AMOUNT])
            for _, r in norm.iterrows()
        }
        self.assertEqual(by_type["zakup papierów"], -1000.0)
        self.assertEqual(by_type["naliczenie odsetek na 2020-02-01"], -50.0)
        self.assertEqual(by_type["wypłata przelewem"], 200.0)
        self.assertEqual(by_type["podatek"], 10.0)


class BondsRoiAndSnapshotTests(unittest.TestCase):
    def test_roi_terminal_from_stan_and_sold(self):
        summary, events = compute_bonds_broker_roi_from_frames(
            _historia_rows(),
            _stan_df(),
            date(2026, 8, 3),
            "obligacjeskarbowe",
        )
        by_id = {r["asset_id"]: r for _, r in summary.iterrows()}
        open_row = by_id["obligacjeskarbowe:EDO1029"]
        self.assertFalse(bool(open_row["is_sold"]))
        self.assertAlmostEqual(float(open_row["terminal_unrealized"]), 82550.0)

        sold_row = by_id["obligacjeskarbowe:COI0723"]
        self.assertTrue(bool(sold_row["is_sold"]))
        self.assertAlmostEqual(float(sold_row["terminal_unrealized"]), 0.0)
        self.assertIn("obligacjeskarbowe:EDO1029", events)

    def test_evaluate_single_mtm_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            asset_dir = Path(tmp) / "obligacjeskarbowe"
            asset_dir.mkdir()
            row = _catalog_row()

            with patch(
                "evaluators.evaluate_broker_obligacje.resolve_asset_dir",
                return_value=asset_dir,
            ), patch(
                "evaluators.evaluate_broker_obligacje.read_obligacje_stan",
                return_value=_stan_df(),
            ):
                result, warnings = evaluate_broker_obligacje(
                    Path(tmp), "obligacjeskarbowe", row, date(2026, 8, 3)
                )

            self.assertEqual(len(result), 1)
            self.assertAlmostEqual(float(result.iloc[0][AssetsDef.VALUE]), 82550.0)
            self.assertEqual(result.iloc[0][AssetsDef.TYPE], TypeDomain.BONDS)
            self.assertEqual(warnings, [])

    def test_is_obligacje_broker(self):
        self.assertTrue(is_obligacje_broker(_catalog_row()))
        other = _catalog_row()
        other[AssetsDef.ID] = "p_re_robo"
        other[AssetsDef.TYPE] = TypeDomain.EQUITIES
        self.assertFalse(is_obligacje_broker(other))


if __name__ == "__main__":
    unittest.main()
