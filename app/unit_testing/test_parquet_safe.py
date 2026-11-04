import tempfile
import unittest
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from data_step.parquet_safe import (
    dataframe_for_parquet,
    read_dataframe_parquet,
    write_dataframe_parquet,
)
from evaluators.valuation_date import filter_on_or_before


class DataframeForParquetTests(unittest.TestCase):
    def test_stringdtype_becomes_object(self):
        df = pd.DataFrame(
            {
                "nan_str": pd.Series(["a", np.nan], dtype=pd.StringDtype(na_value=np.nan)),
                "na_str": pd.Series(["b", pd.NA], dtype=pd.StringDtype(na_value=pd.NA)),
                "num": [1.5, 2.5],
            }
        )
        out = dataframe_for_parquet(df)
        self.assertEqual(out["nan_str"].dtype, object)
        self.assertEqual(out["na_str"].dtype, object)
        self.assertTrue(pd.api.types.is_float_dtype(out["num"]))
        self.assertIsNone(out["nan_str"].iloc[1])
        self.assertIsNone(out["na_str"].iloc[1])

    def test_mixed_object_column_is_stringified(self):
        df = pd.DataFrame({"obj": ["x", 1, None]})
        out = dataframe_for_parquet(df)
        self.assertEqual(list(out["obj"]), ["x", "1", None])


class WriteDataframeParquetTests(unittest.TestCase):
    def test_large_string_frame_writes_without_threads_crash(self):
        n = 5000
        df = pd.DataFrame(
            {
                "nan_str": pd.Series(["a"] * n, dtype=pd.StringDtype(na_value=np.nan)),
                "na_str": pd.Series(["b"] * (n - 1) + [pd.NA], dtype=pd.StringDtype(na_value=pd.NA)),
                "num": np.arange(n, dtype=float),
            }
        )
        self.assertGreater(len(df), 100 * len(df.columns))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "large.parquet"
            write_dataframe_parquet(df, path)
            loaded = read_dataframe_parquet(path)
        self.assertEqual(len(loaded), n)
        self.assertEqual(loaded["nan_str"].iloc[0], "a")
        self.assertTrue(pd.isna(loaded["na_str"].iloc[-1]) or loaded["na_str"].iloc[-1] in ("", None))

    def test_revolut_like_strings_roundtrip_values(self):
        df = pd.DataFrame(
            {
                "Rodzaj": pd.Series(["Opłata", "Transfer"]),
                "Produkt": pd.Series(["Bieżące", ""]),
                "Kwota": [0.0, 10.5],
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "revolut.parquet"
            write_dataframe_parquet(df, path)
            loaded = read_dataframe_parquet(path)
        self.assertEqual(list(loaded["Rodzaj"]), ["Opłata", "Transfer"])
        self.assertEqual(float(loaded["Kwota"].iloc[1]), 10.5)

    def test_datetime_column_roundtrips_as_iso_string(self):
        df = pd.DataFrame(
            {
                "id": [1, 2, 3],
                "data wyceny": pd.to_datetime(["2026-07-01", "2026-07-08", "2026-07-15"]),
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dates.parquet"
            write_dataframe_parquet(df, path)
            loaded = read_dataframe_parquet(path)
        self.assertEqual(
            loaded["data wyceny"].tolist(),
            ["2026-07-01", "2026-07-08", "2026-07-15"],
        )
        filtered = filter_on_or_before(loaded, "data wyceny", date(2026, 7, 10))
        self.assertEqual(filtered["id"].tolist(), [1, 2])


if __name__ == "__main__":
    unittest.main()
