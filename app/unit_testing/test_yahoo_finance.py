import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from data_step.data_step import DATA_STEP
from yahoo_finance.data_model import yahoo_ticker_resource
from yahoo_finance.repository import download_yahoo


def _yf_close(dates: list[str], values: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"Close": values}, index=pd.to_datetime(dates))


class YahooFinanceTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        root = Path(self._tmpdir.name)
        data_steps = root / "data_steps"
        data_steps.mkdir()
        (data_steps / "_metadata.json").write_text("{}", encoding="utf-8")
        start_file = root / "app" / "module.py"
        start_file.parent.mkdir(parents=True)
        start_file.touch()
        DATA_STEP.init_steps(root=start_file)
        self.data_steps = data_steps

    def tearDown(self):
        self._tmpdir.cleanup()

    @patch("yahoo_finance.fetch.yf.download")
    def test_first_obtain_fetches_second_is_cached(self, mock_download):
        mock_download.return_value = _yf_close(
            ["2020-01-02", "2020-01-03"],
            [100.0, 101.0],
        )

        first = download_yahoo(["SPY"], start="2020-01-01", end="2020-01-10")
        second = download_yahoo(["SPY"], start="2020-01-01", end="2020-01-10")

        self.assertEqual(mock_download.call_count, 1)
        pd.testing.assert_frame_equal(first, second)
        self.assertEqual(list(first.columns), ["SPY"])
        self.assertEqual(len(first), 2)

    @patch("yahoo_finance.fetch.yf.download")
    def test_different_as_of_fetches_again_and_drops_old(self, mock_download):
        mock_download.side_effect = [
            _yf_close(["2020-01-02"], [100.0]),
            _yf_close(["2020-01-02", "2020-01-03"], [100.0, 101.0]),
        ]

        download_yahoo(["SPY"], start="2020-01-01", end="2020-01-10")
        download_yahoo(["SPY"], start="2020-01-01", end="2020-01-11")

        self.assertEqual(mock_download.call_count, 2)
        spy_dir = self.data_steps / "yahoo" / "SPY"
        self.assertTrue((spy_dir / "2020-01-11.parquet").is_file())
        self.assertFalse((spy_dir / "2020-01-10.parquet").is_file())

    @patch("yahoo_finance.fetch.yf.download")
    def test_joins_multiple_tickers(self, mock_download):
        mock_download.side_effect = [
            _yf_close(["2020-01-02", "2020-01-03"], [10.0, 11.0]),
            _yf_close(["2020-01-02", "2020-01-03"], [1.1, 1.2]),
        ]

        result = download_yahoo(
            ["SPY", "EURUSD=X"],
            start="2020-01-01",
            end="2020-01-10",
        )

        self.assertEqual(list(result.columns), ["SPY", "EURUSD=X"])
        self.assertEqual(result.loc[pd.Timestamp("2020-01-03"), "SPY"], 11.0)
        self.assertEqual(result.loc[pd.Timestamp("2020-01-03"), "EURUSD=X"], 1.2)
        self.assertTrue(
            (self.data_steps / "yahoo" / "EURUSD_X" / "2020-01-10.parquet").is_file()
        )
        self.assertEqual(
            yahoo_ticker_resource("EURUSD=X", pd.Timestamp("2020-01-10").date()),
            "yahoo/EURUSD_X/2020-01-10.parquet",
        )

    @patch("yahoo_finance.fetch.yf.download")
    def test_single_ticker_is_one_column(self, mock_download):
        mock_download.return_value = _yf_close(["2020-01-02"], [42.0])

        result = download_yahoo(["XEON.DE"], start="2020-01-01", end="2020-01-10")

        self.assertEqual(list(result.columns), ["XEON.DE"])
        self.assertEqual(result.iloc[0, 0], 42.0)

    @patch("yahoo_finance.fetch.yf.download")
    def test_empty_series_raises(self, mock_download):
        mock_download.return_value = pd.DataFrame()

        with self.assertRaises(ValueError):
            download_yahoo(["MISSING"], start="2020-01-01", end="2020-01-10")

    def test_empty_tickers_raises(self):
        with self.assertRaises(ValueError):
            download_yahoo([])


if __name__ == "__main__":
    unittest.main()
