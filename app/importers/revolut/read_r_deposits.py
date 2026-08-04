# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

import re
from pathlib import Path

import pandas as pd

from data_step.data_step import DATA_STEP
from importers.deduplicate_records import deduplicate_records
from importers.revolut.deposit_data_model import RevolutDepositFile
from importers.revolut.savings_statement import (
    assert_no_coverage_gaps,
    empty_savings_frame,
    is_savings_statement_filename,
    normalize_savings_statement,
    parse_savings_period,
    savings_unique_key,
)

_UUID_DEPOSIT_NAME = re.compile(r"^.{8}-.{4}-.{4}-.{4}-.{12}\.csv$", re.IGNORECASE)


def read_revolut_deposit_transactions(input_path: Path, asset_id: str) -> pd.DataFrame:
    resource = f"01 source/{asset_id}-deposit.parquet"
    r = DATA_STEP.obtain_dependent(resource, _read_revolut_deposit_transactions, input_path, asset_id=asset_id)
    result = r.data_frame()
    return result


def _read_revolut_deposit_transactions(source_file: Path = None, asset_id: str = "") -> pd.DataFrame:
    if source_file is None or not source_file.is_dir():
        return empty_savings_frame()

    savings_files = sorted(
        f for f in source_file.iterdir()
        if f.is_file() and is_savings_statement_filename(f.name)
    )
    uuid_files = sorted(
        f for f in source_file.iterdir()
        if f.is_file() and _UUID_DEPOSIT_NAME.match(f.name)
    )

    # Preferowane źródło: savings-statement (ROI + NAV). UUID = legacy gdy brak savings.
    if savings_files:
        return _read_savings_files(savings_files, asset_id=asset_id)
    if uuid_files:
        return _read_uuid_files(uuid_files)
    return empty_savings_frame()


def _read_savings_files(input_files: list[Path], *, asset_id: str) -> pd.DataFrame:
    periods = [parse_savings_period(path) for path in input_files]
    assert_no_coverage_gaps(periods, asset_id=asset_id)

    records: list[pd.DataFrame] = []
    for input_file, (period_start, period_end) in zip(input_files, periods):
        raw = pd.read_csv(input_file)
        df = normalize_savings_statement(raw, period_start=period_start, period_end=period_end)
        print(f"PLIK:{input_file} {len(df):>4} rekord/ów (savings)")
        if not df.empty:
            records.append(df)

    if not records:
        return empty_savings_frame()

    result = records[0]
    for record in records[1:]:
        result = deduplicate_records(
            result,
            record,
            RevolutDepositFile.DATE,
            savings_unique_key(),
        )

    result[RevolutDepositFile.FILE_DATE] = ""
    RevolutDepositFile.check_structure(result)
    return result


def _read_uuid_files(input_files: list[Path]) -> pd.DataFrame:
    records: list[pd.DataFrame] = []
    for input_file in input_files:
        df = pd.read_csv(input_file)
        df = RevolutDepositFile.normalize_dtypes(df)
        print(f"PLIK:{input_file} {len(df):>4} rekord/ów (uuid)")
        records.append(df)

    result = records[0]
    for record in records[1:]:
        result = deduplicate_records(
            result,
            record,
            RevolutDepositFile.COMPLETED_DATE,
            RevolutDepositFile.unique_key(),
        )

    result[RevolutDepositFile.FILE_DATE] = ""
    RevolutDepositFile.check_structure(result)
    return result
