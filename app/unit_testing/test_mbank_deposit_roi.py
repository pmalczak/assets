# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from evaluators.evaluate_mbank import evaluate_mbank
from importers.assets.data_model import AssetsDef, GroupDomain, KindDomain, TypeDomain
from importers.mbank.data_model import MBankFile, MbankOperationType
from roi.categories import CAPEX, DIVESTMENT, OPEX, REVENUES
from roi.data_model import CashFlowEvent
from roi.mbank_deposit_roi import (
    build_mbank_lokata_cashflows,
    compute_lokata_roi,
    compute_mbank_deposit_roi,
    extract_lokata_nr,
    lokata_asset_id,
)


ACCOUNT = "g_m_56_3217_eur"
NR_CLOSED = "NR 170053774600002"
NR_OPEN = "NR 170053774600007"
ASSET_CLOSED = lokata_asset_id(ACCOUNT, NR_CLOSED)
ASSET_OPEN = lokata_asset_id(ACCOUNT, NR_OPEN)


def _row(
    tx_date: str,
    opis: str,
    title: str,
    amount: float,
    *,
    party: str = "",
    account: str = "",
) -> dict:
    return {
        MBankFile.MBANK_TRANSACTION_DATE: tx_date,
        MBankFile.MBANK_DESCRIPTION: opis,
        MBankFile.MBANK_TITLE: title,
        MBankFile.MBANK_AMOUNT: amount,
        MBankFile.MBANK_TRANSACTION_PARTY: party,
        MBankFile.MBANK_ACCOUNT_NUMBER: account,
    }


def _closed_cycle() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _row(
                "2025-09-12",
                MbankOperationType.PRZELEW_WEWNETRZNY_WYCHODZACY,
                f"OTW. LOKATY {NR_CLOSED}",
                -100000.0,
            ),
            _row(
                "2025-10-01",
                MbankOperationType.PODATEK_OD_ODSETEK_KAPITALOWYCH,
                NR_CLOSED,
                -0.10,
            ),
            _row(
                "2025-10-01",
                MbankOperationType.ZERWANIE_LOKATY_TERMINOWEJ,
                NR_CLOSED,
                100000.0,
            ),
            _row(
                "2025-10-01",
                MbankOperationType.ODSETKI_LOKAT_TERMINOWYCH,
                NR_CLOSED,
                0.52,
            ),
        ]
    )


def _open_with_interest() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _row(
                "2025-09-12",
                MbankOperationType.PRZELEW_WEWNETRZNY_WYCHODZACY,
                f"OTW. LOKATY {NR_OPEN}",
                -100000.0,
            ),
            _row(
                "2026-03-12",
                MbankOperationType.ODSETKI_LOKAT_TERMINOWYCH,
                NR_OPEN,
                4.96,
            ),
            _row(
                "2026-03-12",
                MbankOperationType.PODATEK_OD_ODSETEK_KAPITALOWYCH,
                NR_OPEN,
                -0.94,
            ),
        ]
    )


class ExtractLokataNrTests(unittest.TestCase):
    def test_extracts_nr_from_open_title(self):
        self.assertEqual(extract_lokata_nr(f"OTW. LOKATY {NR_CLOSED}"), NR_CLOSED)

    def test_rejects_proforma_longer_number(self):
        self.assertIsNone(extract_lokata_nr("ZWROT ZA PROFORMA NR 231220211530981295"))


class MbankLokataCashflowTests(unittest.TestCase):
    def test_maps_closed_cycle_categories(self):
        events, warnings = build_mbank_lokata_cashflows(_closed_cycle(), ACCOUNT)
        self.assertEqual(warnings, [])
        self.assertIn(ASSET_CLOSED, events)
        cf = events[ASSET_CLOSED]
        by_cat = {
            row[CashFlowEvent.CATEGORY]: row[CashFlowEvent.AMOUNT]
            for _, row in cf.iterrows()
        }
        self.assertAlmostEqual(by_cat[CAPEX], -100000.0)
        self.assertAlmostEqual(by_cat[DIVESTMENT], 100000.0)
        self.assertAlmostEqual(by_cat[REVENUES], 0.52)
        self.assertAlmostEqual(by_cat[OPEX], -0.10)
        self.assertEqual(len(cf), 4)

    def test_skips_internal_transfer_without_otw(self):
        df = pd.DataFrame(
            [
                _row(
                    "2025-01-01",
                    MbankOperationType.PRZELEW_WEWNETRZNY_WYCHODZACY,
                    "ZASILENIE EMAXA",
                    -50.0,
                )
            ]
        )
        events, warnings = build_mbank_lokata_cashflows(df, ACCOUNT)
        self.assertEqual(events, {})
        self.assertEqual(warnings, [])

    def test_skips_ror_tax_without_nr(self):
        df = pd.concat(
            [
                _open_with_interest(),
                pd.DataFrame(
                    [
                        _row(
                            "2025-10-01",
                            MbankOperationType.PODATEK_OD_ODSETEK_KAPITALOWYCH,
                            "",
                            -2.0,
                        )
                    ]
                ),
            ],
            ignore_index=True,
        )
        events, _warnings = build_mbank_lokata_cashflows(df, ACCOUNT)
        cf = events[ASSET_OPEN]
        opex_rows = cf[cf[CashFlowEvent.CATEGORY] == OPEX]
        self.assertEqual(len(opex_rows), 1)
        self.assertAlmostEqual(float(opex_rows.iloc[0][CashFlowEvent.AMOUNT]), -0.94)

    def test_skips_proforma_false_nr(self):
        df = pd.DataFrame(
            [
                _row(
                    "2022-01-27",
                    MbankOperationType.PRZELEW_WEWNETRZNY_PRZYCHODZACY,
                    "ZWROT ZA PROFORMA NR 231220211530981295",
                    4293.49,
                )
            ]
        )
        events, warnings = build_mbank_lokata_cashflows(df, ACCOUNT)
        self.assertEqual(events, {})
        self.assertEqual(warnings, [])

    def test_unknown_opis_on_known_nr_warns(self):
        df = pd.concat(
            [
                _open_with_interest(),
                pd.DataFrame(
                    [
                        _row(
                            "2025-09-13",
                            MbankOperationType.PRZELEW_WEWNETRZNY_PRZYCHODZACY,
                            NR_OPEN,
                            10.0,
                        )
                    ]
                ),
            ],
            ignore_index=True,
        )
        events, warnings = build_mbank_lokata_cashflows(df, ACCOUNT)
        self.assertIn(ASSET_OPEN, events)
        self.assertTrue(any("Nieznany opis" in msg for msg in warnings))
        self.assertNotIn(
            MbankOperationType.PRZELEW_WEWNETRZNY_PRZYCHODZACY,
            events[ASSET_OPEN][CashFlowEvent.DESCRIPTION].tolist(),
        )


class LokataRoiIdentityTests(unittest.TestCase):
    def test_open_without_interest_terminal_equals_minus_capex(self):
        df = pd.DataFrame(
            [
                _row(
                    "2025-09-12",
                    MbankOperationType.PRZELEW_WEWNETRZNY_WYCHODZACY,
                    f"OTW. LOKATY {NR_OPEN}",
                    -100000.0,
                )
            ]
        )
        events, _ = build_mbank_lokata_cashflows(df, ACCOUNT)
        summary = compute_lokata_roi(ASSET_OPEN, events[ASSET_OPEN], date(2025, 9, 12))
        self.assertFalse(summary.is_sold)
        self.assertAlmostEqual(summary.terminal_unrealized, -summary.capex)
        self.assertAlmostEqual(summary.terminal_unrealized, 100000.0)
        self.assertAlmostEqual(summary.roi_nominal, 0.0)

    def test_open_after_interest_terminal_stays_capital(self):
        events, _ = build_mbank_lokata_cashflows(_open_with_interest(), ACCOUNT)
        summary = compute_lokata_roi(ASSET_OPEN, events[ASSET_OPEN], date(2026, 3, 12))
        self.assertFalse(summary.is_sold)
        self.assertAlmostEqual(summary.terminal_unrealized, 100000.0)
        self.assertAlmostEqual(summary.revenue + summary.opex, 4.02)
        self.assertAlmostEqual(summary.roi_nominal, summary.revenue + summary.opex)
        flows = float(events[ASSET_OPEN][CashFlowEvent.AMOUNT].sum())
        self.assertAlmostEqual(summary.roi_nominal, flows + summary.terminal_unrealized)

    def test_zerwanie_terminates_and_keeps_pnl_in_cf(self):
        events, _ = build_mbank_lokata_cashflows(_closed_cycle(), ACCOUNT)
        cf = events[ASSET_CLOSED]
        summary = compute_lokata_roi(ASSET_CLOSED, cf, date(2025, 10, 1))
        self.assertTrue(summary.is_sold)
        self.assertAlmostEqual(summary.terminal_unrealized, 0.0)
        self.assertAlmostEqual(summary.capex + summary.terminal_realized, 0.0, delta=0.01)
        self.assertAlmostEqual(summary.roi_nominal, summary.revenue + summary.opex)
        self.assertAlmostEqual(summary.roi_nominal, 0.42)
        self.assertEqual(int((cf[CashFlowEvent.CATEGORY] == DIVESTMENT).sum()), 1)

    def test_before_close_still_open(self):
        events, _ = build_mbank_lokata_cashflows(_closed_cycle(), ACCOUNT)
        summary = compute_lokata_roi(ASSET_CLOSED, events[ASSET_CLOSED], date(2025, 9, 12))
        self.assertFalse(summary.is_sold)
        self.assertAlmostEqual(summary.terminal_unrealized, 100000.0)


class ComputeMbankDepositRoiTests(unittest.TestCase):
    def test_two_lokaty_from_statements(self):
        statement = pd.concat([_closed_cycle(), _open_with_interest()], ignore_index=True)
        summary, events, warnings = compute_mbank_deposit_roi(
            date(2026, 3, 12),
            statements={ACCOUNT: statement},
        )
        self.assertIn(ASSET_CLOSED, events)
        self.assertIn(ASSET_OPEN, events)
        by_id = summary.set_index("asset_id")
        self.assertTrue(bool(by_id.loc[ASSET_CLOSED, "is_sold"]))
        self.assertFalse(bool(by_id.loc[ASSET_OPEN, "is_sold"]))
        self.assertEqual(int(by_id.loc[ASSET_OPEN, "terminal_unrealized"]), 100000)
        self.assertFalse(any("snapshot NAV" in msg for msg in warnings))

    def test_wygasniecie_also_terminates(self):
        df = pd.DataFrame(
            [
                _row(
                    "2025-01-01",
                    MbankOperationType.PRZELEW_WEWNETRZNY_WYCHODZACY,
                    f"OTW. LOKATY {NR_OPEN}",
                    -5000.0,
                ),
                _row(
                    "2025-06-01",
                    MbankOperationType.WYGASNIECIE_LOKATY_TERMINOWEJ,
                    NR_OPEN,
                    5000.0,
                ),
            ]
        )
        summary, _events, _warnings = compute_mbank_deposit_roi(
            date(2025, 6, 1),
            statements={ACCOUNT: df},
        )
        self.assertTrue(bool(summary.iloc[0]["is_sold"]))
        self.assertEqual(int(summary.iloc[0]["terminal_unrealized"]), 0)


def _statement_for_evaluate(rows: pd.DataFrame) -> pd.DataFrame:
    work = rows.copy()
    work[MBankFile.DEBIT_ACCOUNT] = "PL00"
    work[MBankFile.MBANK_OUTSTANDING_BALANCE] = 1.0
    work[MBankFile.FILE_DATE] = "2026-03-12"
    return work


class EvaluateMbankDepositSnapshotTests(unittest.TestCase):
    def _catalog(self) -> pd.Series:
        return pd.Series(
            {
                AssetsDef.ID: ACCOUNT,
                AssetsDef.TYPE: TypeDomain.CURRENT_ACCOUNT,
                AssetsDef.GROUP: GroupDomain.BANK_ACCOUNTS,
                AssetsDef.DESCR: "mbank eur",
                AssetsDef.KIND: KindDomain.MBANK + ".GM",
                AssetsDef.CURRENCY: "EUR",
                AssetsDef.NOTES: "",
            }
        )

    def _evaluate(self, statement: pd.DataFrame, valuation: date = date(2026, 3, 12)):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ACCOUNT).mkdir()
            with (
                patch(
                    "evaluators.evaluate_mbank.read_m_transactions",
                    return_value=_statement_for_evaluate(statement),
                ),
                patch(
                    "evaluators.evaluate_mbank.resolve_asset_dir",
                    return_value=root / ACCOUNT,
                ),
            ):
                return evaluate_mbank(root, ACCOUNT, self._catalog(), valuation)

    def test_one_deposit_row_per_account_is_open_capital(self):
        statement = pd.concat([_closed_cycle(), _open_with_interest()], ignore_index=True)
        result = self._evaluate(statement)
        deposits = result[result[AssetsDef.TYPE] == TypeDomain.DEPOSIT]
        self.assertEqual(len(deposits), 1)
        row = deposits.iloc[0]
        self.assertEqual(row[AssetsDef.ID], ACCOUNT)
        self.assertAlmostEqual(float(row[AssetsDef.VALUE]), 100000.0)
        self.assertEqual(row[AssetsDef.DESCR], "depozyty (1 lokata)")
        self.assertEqual(row[AssetsDef.GROUP], GroupDomain.DEPOSIT)

    def test_interest_does_not_change_snapshot_nav(self):
        result = self._evaluate(_open_with_interest())
        deposits = result[result[AssetsDef.TYPE] == TypeDomain.DEPOSIT]
        self.assertEqual(len(deposits), 1)
        self.assertAlmostEqual(float(deposits.iloc[0][AssetsDef.VALUE]), 100000.0)

    def test_all_closed_omits_deposit_row(self):
        result = self._evaluate(_closed_cycle(), date(2025, 10, 1))
        deposits = result[result[AssetsDef.TYPE] == TypeDomain.DEPOSIT]
        self.assertTrue(deposits.empty)
