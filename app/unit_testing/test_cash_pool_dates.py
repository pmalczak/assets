import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pandas as pd

from app_streamlit.render_main_reports import CASH_POOL_DISPLAY_COLUMNS, cash_pool_table_for_display
from evaluators.evaluate_assets import evaluate_assets
from evaluators.evaluate_mbank import evaluate_mbank
from evaluators.evaluate_revolut import evaluate_revolut
from fx.data_model import LastFx
from importers.assets.data_model import AssetsDef, AssetsFile, TypeDomain
from importers.mbank.data_model import MBankFile
from importers.revolut.account_data_model import RevolutAccountFile
from importers.revolut.revolut_file_state import RevolutFileState
from importers.statement_download_date import download_date_of
from nbp_fx_repo.nbp_fx_repository import NBP_API_EUR


def _catalog_row(asset_id: str, kind: str, currency: str = "PLN") -> pd.Series:
    return pd.Series(
        {
            AssetsFile.ID: asset_id,
            AssetsFile.TYPE: TypeDomain.CURRENT_ACCOUNT,
            AssetsFile.GROUP: "1 konta bankowe",
            AssetsFile.DESCR: asset_id,
            AssetsFile.KIND: kind,
            AssetsFile.CURRENCY: currency,
            AssetsFile.NOTES: "",
        }
    )


def _empty_mbank_row(txn_date: str, balance: float) -> dict:
    return {
        MBankFile.MBANK_BOOKING_DATE: txn_date,
        MBankFile.MBANK_TRANSACTION_DATE: txn_date,
        MBankFile.MBANK_DESCRIPTION: "",
        MBankFile.MBANK_TITLE: "",
        MBankFile.MBANK_TRANSACTION_PARTY: "",
        MBankFile.MBANK_ACCOUNT_NUMBER: "",
        MBankFile.MBANK_AMOUNT: 0.0,
        MBankFile.MBANK_OUTSTANDING_BALANCE: balance,
        MBankFile.EFFECTIVE_DATE: txn_date,
        MBankFile.DEBIT_ACCOUNT: "PL00",
        MBankFile.FILE_DATE: "",
    }


class FileDateIsDownloadDateTests(unittest.TestCase):
    def test_mbank_file_date_is_download_not_period_end(self):
        from importers.mbank.read_m_transactions import _read_m_transactions

        def _fake_read(path, **_kwargs):
            end = path.stem.rsplit("_", 1)[-1]
            return pd.DataFrame([_empty_mbank_row(f"2026-{end[4:6]}-{end[6:8]}", 10.0)]), end

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "acc_20260101_20260301.csv"
            b = root / "acc_20260401_20260601.csv"
            a.write_text("x", encoding="utf-8")
            b.write_text("x", encoding="utf-8")
            with patch(
                "importers.mbank.read_m_transactions.read_mbank_csv_file",
                side_effect=_fake_read,
            ):
                df = _read_m_transactions(source_file=root)
            fetched = max(download_date_of(a), download_date_of(b)).isoformat()
        self.assertEqual(df[MBankFile.FILE_DATE].iloc[0], fetched)
        self.assertNotEqual(df[MBankFile.FILE_DATE].iloc[0], "20260301")

    def test_revolut_file_date_is_download_not_period_end(self):
        from importers.revolut.read_r_transactions import _read_revolut_account_transactions

        def _account_csv(path: Path, end: str, amount: float) -> None:
            pd.DataFrame(
                [
                    {
                        RevolutAccountFile.KIND: "Transfer",
                        RevolutAccountFile.PRODUCT: "Current",
                        RevolutAccountFile.INIT_DATE: f"{end} 10:00:00",
                        RevolutAccountFile.DATE: f"{end} 10:00:00",
                        RevolutAccountFile.DESCRIPTION: "x",
                        RevolutAccountFile.AMOUNT: amount,
                        RevolutAccountFile.FEE: 0,
                        RevolutAccountFile.CURRENCY: "PLN",
                        RevolutAccountFile.STATE: RevolutFileState.CLOSED,
                        RevolutAccountFile.BALANCE: amount,
                    }
                ]
            ).to_csv(path, index=False)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            p1 = root / "account-statement_2026-01-01_2026-03-01.csv"
            p2 = root / "account-statement_2026-04-01_2026-06-01.csv"
            _account_csv(p1, "2026-03-01", 1.0)
            _account_csv(p2, "2026-06-01", 2.0)
            df = _read_revolut_account_transactions(source_file=root)
            fetched = max(download_date_of(p1), download_date_of(p2)).isoformat()
        self.assertEqual(df[RevolutAccountFile.FILE_DATE].iloc[0], fetched)
        self.assertNotEqual(df[RevolutAccountFile.FILE_DATE].iloc[0], "2026-03-01")


class EvaluateMbankCashPoolDatesTests(unittest.TestCase):
    def test_sets_statement_and_last_transaction_dates(self):
        tx = pd.DataFrame(
            [
                {
                    **_empty_mbank_row("2026-08-01", 100.0),
                    MBankFile.FILE_DATE: "2026-07-15",
                },
                {
                    **_empty_mbank_row("2026-09-01", 120.0),
                    MBankFile.FILE_DATE: "2026-07-15",
                },
            ]
        )
        row = _catalog_row("p_m_test", "mbank.PM")
        with patch("evaluators.evaluate_mbank.read_m_transactions", return_value=tx):
            with patch("evaluators.evaluate_mbank.resolve_asset_dir", return_value=Path(".")):
                with patch("evaluators.evaluate_mbank._evaluate_deposits_mbank", return_value=[]):
                    result = evaluate_mbank(Path("."), "p_m_test", row, date(2026, 9, 10))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[AssetsDef.STATEMENT_DATE].iloc[0], "2026-07-15")
        self.assertEqual(result[AssetsDef.LAST_TRANSACTION_DATE].iloc[0], "2026-09-01")
        self.assertEqual(result[AssetsDef.EVALUATION_DATE].iloc[0], "2026-09-01")
        self.assertEqual(float(result[AssetsDef.VALUE].iloc[0]), 120.0)


class EvaluateRevolutCashPoolDatesTests(unittest.TestCase):
    def test_sets_statement_and_last_transaction_dates(self):
        row = _catalog_row("p_re_pln", "revolut.PM", "PLN")
        fake_dir = MagicMock()
        fake_dir.is_dir.return_value = True
        full_tx = pd.DataFrame(
            [
                {
                    RevolutAccountFile.KIND: "Transfer",
                    RevolutAccountFile.PRODUCT: "Current",
                    RevolutAccountFile.INIT_DATE: "2026-08-20",
                    RevolutAccountFile.DATE: "2026-08-20",
                    RevolutAccountFile.DESCRIPTION: "x",
                    RevolutAccountFile.AMOUNT: 50.0,
                    RevolutAccountFile.FEE: 0,
                    RevolutAccountFile.CURRENCY: "PLN",
                    RevolutAccountFile.STATE: RevolutFileState.CLOSED,
                    RevolutAccountFile.BALANCE: 50.0,
                    RevolutAccountFile.FILE_DATE: "2026-08-01",
                },
                {
                    RevolutAccountFile.KIND: "Transfer",
                    RevolutAccountFile.PRODUCT: "Current",
                    RevolutAccountFile.INIT_DATE: "2026-08-31",
                    RevolutAccountFile.DATE: "2026-08-31",
                    RevolutAccountFile.DESCRIPTION: "y",
                    RevolutAccountFile.AMOUNT: 30.0,
                    RevolutAccountFile.FEE: 0,
                    RevolutAccountFile.CURRENCY: "PLN",
                    RevolutAccountFile.STATE: RevolutFileState.CLOSED,
                    RevolutAccountFile.BALANCE: 80.0,
                    RevolutAccountFile.FILE_DATE: "2026-08-01",
                },
            ]
        )
        with patch("evaluators.evaluate_revolut.read_revolut_account_transactions", return_value=full_tx):
            with patch(
                "evaluators.evaluate_revolut.read_revolut_deposit_transactions",
                return_value=pd.DataFrame(),
            ):
                with patch("evaluators.evaluate_revolut.resolve_asset_dir", return_value=fake_dir):
                    result = evaluate_revolut("p_re_pln", row, date(2026, 9, 10))
        self.assertEqual(result[AssetsDef.STATEMENT_DATE].iloc[0], "2026-08-01")
        self.assertEqual(result[AssetsDef.LAST_TRANSACTION_DATE].iloc[0], "2026-08-31")
        self.assertEqual(result[AssetsDef.EVALUATION_DATE].iloc[0], "2026-08-31")


class CashPoolDaysAfterValuationTests(unittest.TestCase):
    def test_days_use_statement_date_for_cash_pool(self):
        catalog = pd.DataFrame(
            [
                {
                    AssetsFile.ID: "p_m_1",
                    AssetsFile.TYPE: TypeDomain.CURRENT_ACCOUNT,
                    AssetsFile.GROUP: "1 konta bankowe",
                    AssetsFile.DESCR: "x",
                    AssetsFile.KIND: "mbank.PM",
                    AssetsFile.CURRENCY: "EUR",
                    AssetsFile.NOTES: "",
                }
            ]
        )
        evaluated = pd.DataFrame(
            [
                {
                    AssetsFile.ID: "p_m_1",
                    AssetsFile.TYPE: TypeDomain.CURRENT_ACCOUNT,
                    AssetsFile.GROUP: "1 konta bankowe",
                    AssetsFile.DESCR: "x",
                    AssetsFile.KIND: "mbank.PM",
                    AssetsFile.CURRENCY: "EUR",
                    AssetsFile.NOTES: "",
                    AssetsDef.IBAN: "",
                    AssetsDef.EVALUATION_DATE: "2026-09-01",
                    AssetsDef.VALUE: 10.0,
                    AssetsDef.STATEMENT_DATE: "2026-08-01",
                    AssetsDef.LAST_TRANSACTION_DATE: "2026-09-01",
                }
            ]
        )
        fx_rates = pd.DataFrame({NBP_API_EUR: [4.0]}, index=pd.to_datetime(["2026-09-10"]))
        fx_rows = pd.DataFrame(
            [
                {AssetsDef.CURRENCY: "EUR", LastFx.FX: 4.0, AssetsDef.VALUE_DATE: "2026-09-10"},
                {AssetsDef.CURRENCY: "PLN", LastFx.FX: 1.0, AssetsDef.VALUE_DATE: "2026-09-10"},
            ]
        )
        with patch("evaluators.evaluate_assets.evaluate_mbank", return_value=evaluated):
            with patch("evaluators.evaluate_assets.get_fx_as_of", return_value=fx_rows):
                result, _warnings = evaluate_assets(
                    Path("."), catalog, fx_rates, date(2026, 9, 11)
                )
        self.assertEqual(int(result[AssetsDef.DAYS_AFTER_VALUATION].iloc[0]), 40)


class CashPoolDisplayColumnsTests(unittest.TestCase):
    def test_hides_evaluation_and_portfolio_valuation_date(self):
        df = pd.DataFrame(
            [
                {
                    AssetsFile.ID: "p_m_1",
                    AssetsFile.DESCR: "x",
                    AssetsFile.CURRENCY: "PLN",
                    AssetsDef.VALUE: 1.0,
                    AssetsDef.VALUE_PLN: 1,
                    AssetsDef.LAST_TRANSACTION_DATE: "2026-09-01",
                    AssetsDef.STATEMENT_DATE: "2026-08-01",
                    AssetsDef.VALUE_DATE: "2026-09-11",
                    AssetsDef.DAYS_AFTER_VALUATION: 41,
                    AssetsDef.PORTFOLIO: "0 OGÓLNY",
                    AssetsDef.EVALUATION_DATE: "2026-09-01",
                    "data_wyceny_portfela": "2026-09-11",
                }
            ]
        )
        shown = cash_pool_table_for_display(df)
        self.assertEqual(list(shown.columns), CASH_POOL_DISPLAY_COLUMNS)
        self.assertIn(AssetsDef.STATEMENT_DATE, shown.columns)
        self.assertNotIn(AssetsDef.EVALUATION_DATE, shown.columns)
        self.assertNotIn(AssetsDef.LAST_TRANSACTION_DATE, shown.columns)
        self.assertNotIn("data_wyceny_portfela", shown.columns)


if __name__ == "__main__":
    unittest.main()
