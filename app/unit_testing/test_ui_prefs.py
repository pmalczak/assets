import tempfile
import unittest
from pathlib import Path

import pandas as pd

from app_proc.ui_prefs import (
    DEFAULT_SOLD_FILTER,
    DEFAULT_TAB,
    SOLD_FILTER_ACTIVE,
    SOLD_FILTER_ALL,
    SOLD_FILTER_SOLD,
    TAB_LABELS,
    filter_by_sold,
    load_last_tab,
    load_sold_filter,
    render_sold_filter_control,
    save_last_tab,
    save_sold_filter,
)


class UiPrefsTests(unittest.TestCase):
    def test_roi_venues_are_not_top_level_tabs(self):
        self.assertIn("ROI", TAB_LABELS)
        self.assertEqual(TAB_LABELS.count("ROI"), 1)
        for label in (
            "ROI Revolut robo",
            "ROI Revolut depozyty",
            "ROI mBank depozyty",
            "ROI obligacje",
            "ROI DEGIRO",
            "ROI XTB",
        ):
            self.assertNotIn(label, TAB_LABELS)

    def test_load_last_tab_returns_default_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_last_tab(Path(tmp)), DEFAULT_TAB)

    def test_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_last_tab("Wyszukiwanie transakcji", prefs_root=root)
            self.assertEqual(load_last_tab(prefs_root=root), "Wyszukiwanie transakcji")

    def test_assets_tab_slug_still_loads_legacy_raporty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "last_tab.txt").write_text("raporty", encoding="utf-8")
            self.assertEqual(load_last_tab(prefs_root=root), DEFAULT_TAB)
            save_last_tab(DEFAULT_TAB, prefs_root=root)
            self.assertEqual((root / "last_tab.txt").read_text(encoding="utf-8").strip(), "raporty")

    def test_load_last_tab_falls_back_on_unknown_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "last_tab.txt").write_text("nieznany", encoding="utf-8")
            self.assertEqual(load_last_tab(prefs_root=root), DEFAULT_TAB)

    def test_save_and_load_import_tab_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_last_tab("Import wyciągów", prefs_root=root)
            self.assertEqual(load_last_tab(prefs_root=root), "Import wyciągów")

    def test_save_and_load_validate_tab_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_last_tab("Waliduj", prefs_root=root)
            self.assertEqual(load_last_tab(prefs_root=root), "Waliduj")

    def test_roi_tab_roundtrip_and_legacy_venue_slugs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_last_tab("ROI", prefs_root=root)
            self.assertEqual(load_last_tab(prefs_root=root), "ROI")
            self.assertEqual((root / "last_tab.txt").read_text(encoding="utf-8").strip(), "roi")
            for slug in (
                "roi-robo",
                "roi-depozyty",
                "roi-mbank-depozyty",
                "roi-obligacje",
                "roi-degiro",
                "roi-xtb",
            ):
                (root / "last_tab.txt").write_text(slug, encoding="utf-8")
                self.assertEqual(load_last_tab(prefs_root=root), "ROI")
            save_last_tab("Global momentum", prefs_root=root)
            self.assertEqual(load_last_tab(prefs_root=root), "Global momentum")


class SoldFilterPrefsTests(unittest.TestCase):
    def test_render_sold_filter_control_is_exported(self):
        self.assertTrue(callable(render_sold_filter_control))

    def test_load_sold_filter_returns_default_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_sold_filter(Path(tmp)), DEFAULT_SOLD_FILTER)

    def test_save_and_load_sold_filter_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_sold_filter(SOLD_FILTER_ACTIVE, prefs_root=root)
            self.assertEqual(load_sold_filter(prefs_root=root), SOLD_FILTER_ACTIVE)
            save_sold_filter(SOLD_FILTER_SOLD, prefs_root=root)
            self.assertEqual(load_sold_filter(prefs_root=root), SOLD_FILTER_SOLD)

    def test_load_sold_filter_falls_back_on_unknown_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sold_filter.txt").write_text("nieznany", encoding="utf-8")
            self.assertEqual(load_sold_filter(prefs_root=root), DEFAULT_SOLD_FILTER)

    def test_filter_by_sold_keeps_matching_rows(self):
        df = pd.DataFrame(
            {
                "asset_id": ["open", "sold", "also-open"],
                "is_sold": [False, True, False],
            }
        )
        active = filter_by_sold(df, SOLD_FILTER_ACTIVE)
        self.assertEqual(list(active["asset_id"]), ["open", "also-open"])
        sold = filter_by_sold(df, SOLD_FILTER_SOLD)
        self.assertEqual(list(sold["asset_id"]), ["sold"])
        all_rows = filter_by_sold(df, SOLD_FILTER_ALL)
        self.assertEqual(list(all_rows["asset_id"]), ["open", "sold", "also-open"])

    def test_filter_by_sold_without_column_is_noop(self):
        df = pd.DataFrame({"asset_id": ["a"]})
        self.assertEqual(len(filter_by_sold(df, SOLD_FILTER_SOLD)), 1)

    def test_filter_by_sold_treats_na_as_not_sold(self):
        df = pd.DataFrame({"asset_id": ["a", "b"], "is_sold": [pd.NA, True]})
        active = filter_by_sold(df, SOLD_FILTER_ACTIVE)
        self.assertEqual(list(active["asset_id"]), ["a"])
