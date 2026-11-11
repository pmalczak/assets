import unittest
import warnings
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from importers.excel_io import _OPENPYXL_NO_DEFAULT_STYLE, read_excel


class ReadExcelEngineTests(unittest.TestCase):
    def test_xls_uses_xlrd(self):
        with patch("importers.excel_io.pd.read_excel", return_value=pd.DataFrame()) as mock:
            read_excel("/tmp/foo.xls")
        self.assertEqual(mock.call_args.kwargs.get("engine"), "xlrd")

    def test_xlsx_uses_openpyxl(self):
        with patch("importers.excel_io.pd.read_excel", return_value=pd.DataFrame()) as mock:
            read_excel("/tmp/foo.xlsx")
        self.assertEqual(mock.call_args.kwargs.get("engine"), "openpyxl")

    def test_explicit_engine_preserved(self):
        with patch("importers.excel_io.pd.read_excel", return_value=pd.DataFrame()) as mock:
            read_excel("/tmp/foo.xls", engine="openpyxl")
        self.assertEqual(mock.call_args.kwargs.get("engine"), "openpyxl")

    def test_real_stan_xls_readable(self):
        path = Path.home() / "Dropbox/INWESTYCJE/assets/obligacjeskarbowe/StanRachunkuRejestrowego_2026-09-03.xls"
        if not path.is_file():
            self.skipTest(f"Brak lokalnego pliku: {path}")
        df = read_excel(path)
        self.assertFalse(df.empty)
        self.assertIn("EMISJA", df.columns)

    def test_openpyxl_default_style_warning_silenced_in_read_excel(self):
        def _warn_then_frame(*_a, **_k):
            warnings.warn(_OPENPYXL_NO_DEFAULT_STYLE, UserWarning)
            return pd.DataFrame({"a": [1]})

        with patch("importers.excel_io.pd.read_excel", side_effect=_warn_then_frame):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                read_excel("/tmp/foo.xlsx")
        self.assertEqual(
            [w for w in caught if _OPENPYXL_NO_DEFAULT_STYLE in str(w.message)],
            [],
        )

if __name__ == "__main__":
    unittest.main()
