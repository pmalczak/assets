# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from nbp_fx_repo.nbp_fx_file_cache import NbpFxFileCache


def _cache(root: Path, year: int) -> NbpFxFileCache:
    """Bez sieci — konstruktor NbpFxFileCache od razu woła API."""
    obj = NbpFxFileCache.__new__(NbpFxFileCache)
    obj.target_directory = root
    obj.year = year
    return obj


class NbpFxFileCacheNameTests(unittest.TestCase):
    def test_closed_year_has_stable_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = _cache(Path(tmp), 2024)
            self.assertEqual(cache.parquet_file_name().name, "NBP_FX_RATES.2024.parquet")

    def test_current_year_uses_hour_bucket(self):
        fixed = datetime(2026, 10, 29, 9, 15, 0)
        with tempfile.TemporaryDirectory() as tmp:
            cache = _cache(Path(tmp), 2026)
            with patch(
                "nbp_fx_repo.nbp_fx_file_cache.datetime.datetime"
            ) as dt_cls:
                dt_cls.now.return_value = fixed
                name = cache.parquet_file_name().name
            self.assertEqual(name, "NBP_FX_RATES.2026.10_29_09.parquet")

    def test_delete_outdated_keeps_current_hour_only(self):
        fixed = datetime(2026, 10, 29, 14, 0, 0)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_day = root / "NBP_FX_RATES.2026.10_29.parquet"
            old_hour = root / "NBP_FX_RATES.2026.10_29_09.parquet"
            keep = root / "NBP_FX_RATES.2026.10_29_14.parquet"
            other_year = root / "NBP_FX_RATES.2025.parquet"
            for path in (old_day, old_hour, keep, other_year):
                path.write_text("x", encoding="utf-8")
            cache = _cache(root, 2026)
            with patch(
                "nbp_fx_repo.nbp_fx_file_cache.datetime.datetime"
            ) as dt_cls:
                dt_cls.now.return_value = fixed
                cache.delete_outdated_files()
            self.assertTrue(keep.is_file())
            self.assertTrue(other_year.is_file())
            self.assertFalse(old_day.is_file())
            self.assertFalse(old_hour.is_file())


if __name__ == "__main__":
    unittest.main()
