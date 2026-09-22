import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from data_step.data_step import DATA_STEP
from nbp_pl_api.nbp_gold_fetch import fetch_nbp_gold
from nbp_pl_api.nbp_gold_repository import gold_price_as_of, load_nbp_gold, nbp_gold_resource


def _response(status: int, payload=None):
    class _Resp:
        status_code = status
        content = b""

        def json(self):
            return payload or []

    return _Resp()


class NbpGoldFetchTests(unittest.TestCase):
    @patch("nbp_pl_api.nbp_gold_fetch.requests.get")
    def test_splits_range_at_93_days_and_skips_404(self, mock_get):
        mock_get.side_effect = [
            _response(200, [{"data": "2020-01-02", "cena": 180.5}]),
            _response(404),
            _response(200, [{"data": "2020-07-01", "cena": 200.0}]),
        ]

        series = fetch_nbp_gold(date(2020, 1, 2), date(2020, 7, 6))

        self.assertEqual(mock_get.call_count, 3)
        self.assertEqual(list(series["cena"]), [180.5, 200.0])
        self.assertEqual(
            pd.Timestamp(series.iloc[0]["data"]).date(),
            date(2020, 1, 2),
        )


class NbpGoldRepositoryTests(unittest.TestCase):
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

    @patch("nbp_pl_api.nbp_gold_repository.fetch_nbp_gold")
    def test_first_obtain_fetches_second_is_cached(self, mock_fetch):
        mock_fetch.return_value = pd.DataFrame(
            {"data": pd.to_datetime(["2020-01-02"]), "cena": [180.5]}
        )

        first = load_nbp_gold(date(2020, 1, 10))
        second = load_nbp_gold(date(2020, 1, 10))

        self.assertEqual(mock_fetch.call_count, 1)
        pd.testing.assert_frame_equal(first, second)
        self.assertTrue(
            (self.data_steps / "nbp" / "cenyzlota" / "2020-01-10.parquet").is_file()
        )
        self.assertEqual(
            nbp_gold_resource(date(2020, 1, 10)),
            "nbp/cenyzlota/2020-01-10.parquet",
        )

    @patch("nbp_pl_api.nbp_gold_repository.fetch_nbp_gold")
    def test_newer_as_of_drops_previous_file(self, mock_fetch):
        mock_fetch.return_value = pd.DataFrame(
            {"data": pd.to_datetime(["2020-01-02"]), "cena": [180.5]}
        )

        load_nbp_gold(date(2020, 1, 10))
        load_nbp_gold(date(2020, 1, 11))

        folder = self.data_steps / "nbp" / "cenyzlota"
        self.assertTrue((folder / "2020-01-11.parquet").is_file())
        self.assertFalse((folder / "2020-01-10.parquet").is_file())

    def test_weekend_quote_uses_previous_publication(self):
        series = pd.DataFrame(
            {"data": ["2026-07-03", "2026-07-06"], "cena": [492.22, 500.0]}
        )
        price_date, price = gold_price_as_of(date(2026, 7, 4), series=series)
        self.assertEqual(price_date, date(2026, 7, 3))
        self.assertAlmostEqual(price, 492.22)


if __name__ == "__main__":
    unittest.main()
