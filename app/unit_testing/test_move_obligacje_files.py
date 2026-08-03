import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from importers.pkobp.data_model import PkoBpBonds
from importers.pkobp.historia_dyspozycji import HISTORIA_DYSPOZYCJI_FILE, dated_historia_filename
from maintenance.move_downloaded_results import ACTION_MOVED, ACTION_SKIPPED, KIND_OBLIGACJE
from maintenance.move_obligacje_files import OBLIGACJE_ASSET_ID, move_obligacje_files


def _row(
    day: date,
    *,
    no_line: int = 1,
    bonds_no: int = 10,
    amount: float = 1000.0,
) -> dict:
    return {
        PkoBpBonds.DATE: day,
        PkoBpBonds.ORDER_TYPE: "zakup papierów",
        PkoBpBonds.CODE: "COI0128",
        PkoBpBonds.NO_LINE: no_line,
        PkoBpBonds.SERIES: "A",
        PkoBpBonds.BONDS_NO: bonds_no,
        PkoBpBonds.AMOUNT: amount,
        PkoBpBonds.STAT: "zrealizowana",
        PkoBpBonds.NOTES: "",
    }


def _historia_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


class MoveObligacjeFilesTests(unittest.TestCase):
    def test_moves_stan_and_renames_historia_with_date_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            download = root / "Downloads"
            assets = root / "assets"
            download.mkdir()
            assets.mkdir()

            stan = download / "StanRachunkuRejestrowego_2026-08-03.xls"
            historia_src = download / HISTORIA_DYSPOZYCJI_FILE
            stan.write_bytes(b"stan")
            historia_src.write_bytes(b"historia")
            (download / "other.xls").write_bytes(b"ignore")

            new_df = _historia_df(
                [
                    _row(date(2024, 3, 1), no_line=1),
                    _row(date(2026, 8, 1), no_line=2, bonds_no=5, amount=500.0),
                ]
            )
            expected_historia = dated_historia_filename(date(2024, 3, 1), date(2026, 8, 1))

            with patch(
                "importers.pkobp.historia_dyspozycji.read_historia_excel",
                return_value=new_df,
            ):
                results = move_obligacje_files(assets, download)

            self.assertEqual(len(results), 2)
            self.assertTrue(all(r.action == ACTION_MOVED for r in results))
            self.assertTrue(all(r.kind == KIND_OBLIGACJE for r in results))

            target = assets / OBLIGACJE_ASSET_ID
            self.assertTrue((target / stan.name).is_file())
            self.assertTrue((target / expected_historia).is_file())
            self.assertFalse((target / HISTORIA_DYSPOZYCJI_FILE).exists())
            self.assertFalse(stan.exists())
            self.assertFalse(historia_src.exists())

    def test_skips_and_deletes_historia_when_existing_covers_all_transactions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            download = root / "Downloads"
            assets_root = root / "assets"
            target = assets_root / OBLIGACJE_ASSET_ID
            download.mkdir()
            target.mkdir(parents=True)

            existing_name = dated_historia_filename(date(2020, 1, 1), date(2026, 8, 1))
            existing = target / existing_name
            existing.write_bytes(b"existing")

            historia_src = download / HISTORIA_DYSPOZYCJI_FILE
            historia_src.write_bytes(b"new")

            covering_df = _historia_df(
                [
                    _row(date(2020, 1, 1), no_line=1),
                    _row(date(2024, 3, 1), no_line=2),
                    _row(date(2026, 8, 1), no_line=3),
                ]
            )
            new_df = _historia_df(
                [
                    _row(date(2024, 3, 1), no_line=2),
                    _row(date(2026, 8, 1), no_line=3),
                ]
            )

            def _read(path: Path) -> pd.DataFrame:
                if path == existing:
                    return covering_df
                if path == historia_src:
                    return new_df
                raise AssertionError(path)

            with patch(
                "importers.pkobp.historia_dyspozycji.read_historia_excel",
                side_effect=_read,
            ):
                results = move_obligacje_files(assets_root, download)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].action, ACTION_SKIPPED)
            self.assertEqual(results[0].destination, existing)
            self.assertFalse(historia_src.exists())
            self.assertTrue(existing.is_file())
            self.assertEqual(len(list(target.glob(f"*{HISTORIA_DYSPOZYCJI_FILE}"))), 1)

    def test_overwrites_same_named_historia_when_new_has_extra_transactions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            download = root / "Downloads"
            assets_root = root / "assets"
            target = assets_root / OBLIGACJE_ASSET_ID
            download.mkdir()
            target.mkdir(parents=True)

            dst_name = dated_historia_filename(date(2024, 3, 1), date(2026, 8, 1))
            existing = target / dst_name
            existing.write_bytes(b"old-bytes")

            historia_src = download / HISTORIA_DYSPOZYCJI_FILE
            historia_src.write_bytes(b"new-bytes")

            old_df = _historia_df([_row(date(2024, 3, 1), no_line=1)])
            new_df = _historia_df(
                [
                    _row(date(2024, 3, 1), no_line=1),
                    _row(date(2026, 8, 1), no_line=2, bonds_no=5, amount=500.0),
                ]
            )

            def _read(path: Path) -> pd.DataFrame:
                if path == existing:
                    return old_df
                if path == historia_src:
                    return new_df
                raise AssertionError(path)

            with patch(
                "importers.pkobp.historia_dyspozycji.read_historia_excel",
                side_effect=_read,
            ):
                results = move_obligacje_files(assets_root, download)

            self.assertEqual(results[0].action, ACTION_MOVED)
            self.assertEqual(results[0].destination, existing)
            self.assertFalse(historia_src.exists())
            self.assertEqual(existing.read_bytes(), b"new-bytes")

    def test_noop_when_no_matching_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            download = root / "Downloads"
            assets = root / "assets"
            download.mkdir()
            assets.mkdir()
            (download / "not-bonds.xls").write_bytes(b"x")

            results = move_obligacje_files(assets, download)

            self.assertEqual(results, [])
            self.assertFalse((assets / OBLIGACJE_ASSET_ID).exists())


if __name__ == "__main__":
    unittest.main()
