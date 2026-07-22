import tempfile
import unittest
from pathlib import Path

from app_proc.ui_prefs import DEFAULT_TAB, load_last_tab, save_last_tab


class UiPrefsTests(unittest.TestCase):
    def test_load_last_tab_returns_default_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_last_tab(Path(tmp)), DEFAULT_TAB)

    def test_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_last_tab("Wyszukiwanie transakcji", prefs_root=root)
            self.assertEqual(load_last_tab(prefs_root=root), "Wyszukiwanie transakcji")

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
