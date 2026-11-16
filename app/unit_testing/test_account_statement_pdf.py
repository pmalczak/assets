# -*- coding: utf-8 -*-
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from importers.revolut.account_data_model import RevolutAccountFile
from importers.revolut.account_statement_pdf import (
    convert_revolut_account_statement_pdf,
    csv_name_from_pdf,
    parse_revolut_account_statement_pdf,
    write_revolut_account_statement_csv,
)
from importers.revolut.revolut_file_state import RevolutFileState

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "revolut_account_pdf"
_PDF = _FIXTURES / "2026_11_01_account-statement_2026-10-01_2026-10-31_pl-pl_092cc2.pdf"
_REF_PLN = _FIXTURES / "account-statement_2026-10-01_2026-10-31_pl-pl_b7a7a9.pln.csv"
_REF_EUR = _FIXTURES / "account-statement_2026-10-01_2026-10-31_pl-pl_b7a7a9.eur.csv"

_COMPARE_KEYS = [
    "_date",
    RevolutAccountFile.DESCRIPTION,
    "_amt",
    "_fee",
    "_bal",
    RevolutAccountFile.CURRENCY,
    RevolutAccountFile.KIND,
]


def _norm_for_compare(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["_date"] = out[RevolutAccountFile.DATE].astype(str).str[:10]
    out["_amt"] = out[RevolutAccountFile.AMOUNT].astype(float).round(2)
    out["_fee"] = out[RevolutAccountFile.FEE].astype(float).round(2)
    out["_bal"] = out[RevolutAccountFile.BALANCE].astype(float).round(2)
    return out[_COMPARE_KEYS].sort_values(_COMPARE_KEYS).reset_index(drop=True)


class AccountStatementPdfTests(unittest.TestCase):
    def test_csv_name_strips_generation_prefix(self):
        self.assertEqual(
            csv_name_from_pdf(_PDF.name),
            "account-statement_2026-10-01_2026-10-31_pl-pl_092cc2.csv",
        )

    def test_parse_matches_reference_csv_pln_and_eur(self):
        self.assertTrue(_PDF.is_file(), f"brak fixture PDF: {_PDF}")
        parsed = parse_revolut_account_statement_pdf(_PDF)
        ref = pd.concat(
            [pd.read_csv(_REF_EUR), pd.read_csv(_REF_PLN)],
            ignore_index=True,
        )
        self.assertEqual(len(parsed), len(ref))
        pd.testing.assert_frame_equal(
            _norm_for_compare(parsed),
            _norm_for_compare(ref),
            check_dtype=False,
        )

    def test_parsed_defaults_and_opłata_fee_column(self):
        parsed = parse_revolut_account_statement_pdf(_PDF)
        self.assertTrue((parsed[RevolutAccountFile.PRODUCT] == "Bieżące").all())
        self.assertTrue(
            (parsed[RevolutAccountFile.STATE] == RevolutFileState.CLOSED).all()
        )
        fee_rows = parsed[parsed[RevolutAccountFile.KIND] == "Opłata"]
        self.assertEqual(len(fee_rows), 1)
        self.assertEqual(float(fee_rows.iloc[0][RevolutAccountFile.AMOUNT]), 0.0)
        self.assertAlmostEqual(
            float(fee_rows.iloc[0][RevolutAccountFile.FEE]), 55.99, places=2
        )

    def test_write_csv_roundtrip_columns(self):
        parsed = parse_revolut_account_statement_pdf(_PDF)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "account-statement_2026-10-01_2026-10-31_pl-pl_092cc2.csv"
            write_revolut_account_statement_csv(parsed, out)
            loaded = pd.read_csv(out)
            self.assertNotIn(RevolutAccountFile.FILE_DATE, loaded.columns)
            check = loaded.copy()
            check[RevolutAccountFile.FILE_DATE] = ""
            RevolutAccountFile.check_structure(check)
            currencies = set(
                loaded[RevolutAccountFile.CURRENCY].astype(str).str.upper()
            )
            self.assertEqual(currencies, {"PLN", "EUR"})

    def test_convert_writes_canonical_name_beside_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest_pdf = Path(tmp) / _PDF.name
            dest_pdf.write_bytes(_PDF.read_bytes())
            out = convert_revolut_account_statement_pdf(dest_pdf)
            self.assertEqual(
                out.name,
                "account-statement_2026-10-01_2026-10-31_pl-pl_092cc2.csv",
            )
            self.assertTrue(out.is_file())
            self.assertEqual(out.parent, dest_pdf.parent)


if __name__ == "__main__":
    unittest.main()
