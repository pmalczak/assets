import unittest
from datetime import date

import pandas as pd

from roi.broker_cycle_roi import append_closed_without_cashflows, summarize_broker_cycle_roi
from roi.categories import CAPEX, DIVESTMENT
from roi.data_model import CashFlowEvent


def _row(asset_id: str, day: str, category: str, amount: float) -> dict:
    return {
        CashFlowEvent.ASSET_ID: asset_id,
        CashFlowEvent.DATE: day,
        CashFlowEvent.AMOUNT: amount,
        CashFlowEvent.QUANTITY: None,
        CashFlowEvent.UNIT_PRICE: None,
        CashFlowEvent.CATEGORY: category,
        CashFlowEvent.SOURCE: "t",
        CashFlowEvent.DESCRIPTION: "",
        CashFlowEvent.TITLE: category,
        CashFlowEvent.COUNTERPARTY: "",
        CashFlowEvent.ACCOUNT_NUMBER: "",
    }


class SummarizeBrokerCycleRoiTests(unittest.TestCase):
    def test_closed_cycle_and_open_without_cf(self):
        broker_id = "p_degiro"
        closed_id = f"{broker_id}:ISIN1#2026-06-01"
        events = {
            closed_id: pd.DataFrame(
                [
                    _row(closed_id, "2026-01-01", CAPEX, -100.0),
                    _row(closed_id, "2026-06-01", DIVESTMENT, 110.0),
                ],
                columns=list(CashFlowEvent.COLUMN_ORDER),
            )
        }
        rows = summarize_broker_cycle_roi(
            broker_id=broker_id,
            valuation_date=date(2026, 8, 1),
            events_by_asset=events,
            terminal_by_code={"ISIN2": 50.0},
            qty_by_code={"ISIN2": 1.0},
            eval_date="2026-08-01",
            instrument_name=lambda code: f"name:{code}",
        )
        ids = [r["asset_id"] for r in rows]
        self.assertIn(closed_id, ids)
        self.assertIn(f"{broker_id}:ISIN2", ids)
        sold = next(r for r in rows if r["asset_id"] == closed_id)
        self.assertTrue(sold["is_sold"])
        open_row = next(r for r in rows if r["asset_id"] == f"{broker_id}:ISIN2")
        self.assertFalse(open_row["is_sold"])
        self.assertEqual(open_row["instrument"], "name:ISIN2")

    def test_append_closed_without_cashflows(self):
        broker_id = "p_xtb"
        rows: list[dict] = []
        append_closed_without_cashflows(
            rows,
            broker_id=broker_id,
            valuation_date=date(2026, 8, 1),
            events_by_asset={},
            closed_codes={"AAA.PL"},
            terminal_by_code={},
            qty_by_code={},
            eval_date="2026-08-01",
            instrument_name=lambda c: c,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["asset_id"], f"{broker_id}:AAA.PL")
        self.assertTrue(rows[0]["is_sold"])


if __name__ == "__main__":
    unittest.main()
