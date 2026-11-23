# -*- coding: utf-8 -*-
__author__ = 'pmalczak@gmail.com'

import re
from pathlib import Path
import pandas as pd

from data_step.data_step import DATA_STEP
from importers.deduplicate_records import deduplicate_records
from importers.revolut.account_data_model import RevolutAccountFile
from importers.revolut.revolut_file_state import RevolutFileState
from importers.statement_download_date import iso_download_date

REVOLUT_DATE_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def read_revolut_account_transactions(input_path: Path, asset_id: str) -> pd.DataFrame:
    resource = f'01 source/{asset_id}-account.parquet'
    r = DATA_STEP.obtain_dependent(resource, _read_revolut_account_transactions, input_path)
    result = r.data_frame()
    return result


def _account_statement_period_key(path: Path) -> tuple[str, str, str]:
    """Sort key: okres z nazwy (start, end), potem nazwa — merge chronologiczny."""
    parts = path.stem.split("_")
    start = parts[1] if len(parts) > 1 else ""
    end = parts[2] if len(parts) > 2 else ""
    return (start, end, path.name)


def _read_revolut_account_transactions(source_file: Path = None) -> pd.DataFrame:
    # Sortuj po okresie z nazwy — nieposortowany glob przy dziurach w zakresie dat
    # fałszywie odpala ValueError w dedupe (overlap envelope bez wspólnych kluczy).
    input_files = sorted(
        source_file.glob("account-statement_*.csv"),
        key=_account_statement_period_key,
    )

    if not input_files:
        df = pd.DataFrame(data=None, columns=list(RevolutAccountFile.expected_columns()))
        return df

    download_dates: list[str] = []
    records = []
    for input_file in input_files:
        _extract_file_date(input_file)
        download_dates.append(iso_download_date(input_file))
        df = pd.read_csv(input_file)
        # Dzień kalendarzowy przed dedupe — PDF (00:00:00) i CSV (pełny czas) muszą się schodzić.
        df[RevolutAccountFile.INIT_DATE] = df[RevolutAccountFile.INIT_DATE].apply(_strip_date)
        df[RevolutAccountFile.DATE] = df[RevolutAccountFile.DATE].apply(_strip_date)

        print(f'PLIK:{input_file} {len(df):>4} rekord/ów')
        records += [df]

    result = None
    for record in records:
        if result is None:
            result = record
            continue

        result = deduplicate_records(result, record, RevolutAccountFile.DATE, RevolutAccountFile.unique_key())

    result = result[result[RevolutAccountFile.STATE] == RevolutFileState.CLOSED]
    # data-wyciągu w jednym parquet = max dat pobrań (nie min końca okresu z nazwy).
    result[RevolutAccountFile.FILE_DATE] = max(download_dates) if download_dates else ''
    RevolutAccountFile.check_structure(result)
    return result


def _extract_file_date(input_file):
    parts = Path(input_file).stem.split('_')
    if parts[0] != 'account-statement' or len(parts) < 3:
        raise ValueError(f'Unexpected Revolut account statement name: {input_file.name}')

    end_date = parts[2]
    if not REVOLUT_DATE_PATTERN.match(end_date):
        raise ValueError(f'Unexpected end date in {input_file.name}: {end_date}')
    return end_date


def _strip_date(x):
    """Do ISO dnia `YYYY-MM-DD` (idempotentne dla już obciętych wartości)."""
    if isinstance(x, float) or x is None or (isinstance(x, str) and not str(x).strip()):
        return ''
    s = str(x).strip()
    day = s.split(' ')[0].split('T')[0]
    parts = day.split('-')
    if len(parts) != 3:
        raise ValueError(f'Unexpected Revolut account date: {x!r}')
    return day
