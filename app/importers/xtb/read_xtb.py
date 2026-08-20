# -*- coding: utf-8 -*-
from __future__ import annotations

from io import BytesIO
from datetime import date
from pathlib import Path
import re
import zipfile

import pandas as pd

from importers.xtb.data_model import (
    DEFAULT_XTB_CLIENT_ID,
    XTB_SHEET_CASH_OPERATIONS,
    XTB_SHEET_CLOSED_POSITIONS,
    XTB_SHEET_OPEN_POSITIONS,
    XtbExportSheetInfo,
)

SUPPORTED_XTB_SUFFIXES = {".xlsx", ".xls", ".csv", ".zip"}
_CANONICAL_RE = re.compile(
    r"^xtb_(?P<kind>.+)_(?P<client>\d+)_(?P<start>\d{4}-\d{2}-\d{2})_(?P<end>\d{4}-\d{2}-\d{2})\.(?P<suffix>xlsx|xls|csv)$"
)

_EXPECTED_TABLE_HEADERS = {
    XTB_SHEET_CLOSED_POSITIONS: {"Instrument", "Ticker", "Volume"},
    XTB_SHEET_CASH_OPERATIONS: {"Type", "Instrument", "Ticker", "Time", "Amount"},
    XTB_SHEET_OPEN_POSITIONS: {"Product", "Instrument/Position", "Ticker", "Volume", "Value"},
}


def inspect_xtb_export(path: Path) -> list[XtbExportSheetInfo]:
    """
    Inspect exported XTB reports without assuming their final schema.

    Real XTB samples are still required before mapping columns to the normalized
    broker model. This function intentionally reports sheet names, columns and
    row counts only.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_XTB_SUFFIXES:
        raise ValueError(f"Unsupported XTB export type: {path.name}")
    if suffix == ".zip":
        return _inspect_zip(path)
    return inspect_xtb_export_bytes(path.read_bytes(), suffix, source_name=path.stem)


def inspect_xtb_export_bytes(
    payload: bytes,
    suffix: str,
    *,
    source_name: str = "xtb_export",
) -> list[XtbExportSheetInfo]:
    suffix = suffix.lower()
    if suffix not in SUPPORTED_XTB_SUFFIXES - {".zip"}:
        raise ValueError(f"Unsupported XTB export type: {suffix}")
    if suffix == ".csv":
        df = pd.read_csv(BytesIO(payload))
        return [_sheet_info(source_name, df)]
    return _inspect_excel(BytesIO(payload))


def _inspect_zip(path: Path) -> list[XtbExportSheetInfo]:
    with zipfile.ZipFile(path) as archive:
        export_names = [
            name for name in archive.namelist()
            if Path(name).suffix.lower() in SUPPORTED_XTB_SUFFIXES - {".zip"}
            and not name.endswith("/")
        ]
        if len(export_names) != 1:
            raise ValueError(f"Expected exactly one XTB export file in {path.name}, got {export_names}")
        export_name = export_names[0]
        data = archive.read(export_name)

    suffix = Path(export_name).suffix.lower()
    return inspect_xtb_export_bytes(data, suffix, source_name=Path(export_name).stem)


def _inspect_excel(path: Path) -> list[XtbExportSheetInfo]:
    result = []
    with pd.ExcelFile(path) as workbook:
        for sheet_name in workbook.sheet_names:
            header_row = detect_xtb_header_row(workbook, sheet_name)
            if header_row is None:
                df = workbook.parse(sheet_name=sheet_name)
            else:
                df = workbook.parse(sheet_name=sheet_name, header=header_row)
            result.append(_sheet_info(sheet_name, df, header_row=header_row))
    return result


def detect_xtb_header_row(workbook: pd.ExcelFile, sheet_name: str) -> int | None:
    expected = _EXPECTED_TABLE_HEADERS.get(sheet_name)
    if not expected:
        return None

    preview = workbook.parse(sheet_name=sheet_name, header=None, nrows=30)
    for idx, row in preview.iterrows():
        values = {
            str(value).strip()
            for value in row.tolist()
            if value is not None and not pd.isna(value) and str(value).strip()
        }
        if expected <= values:
            return int(idx)
    return None


def _sheet_info(sheet_name: str, df: pd.DataFrame, header_row: int | None = None) -> XtbExportSheetInfo:
    columns = tuple(str(col).strip() for col in df.columns)
    return XtbExportSheetInfo(sheet_name=sheet_name, columns=columns, rows=len(df), header_row=header_row)


def extract_xtb_report_period(path: Path) -> tuple[date, date]:
    match = _CANONICAL_RE.fullmatch(Path(path).name)
    if not match:
        raise ValueError(f"Unexpected XTB report name: {Path(path).name}")
    return date.fromisoformat(match.group("start")), date.fromisoformat(match.group("end"))


def latest_xtb_report_as_of(
    input_path: Path,
    valuation_date: date,
    *,
    required_kind: str = "open",
    client_id: str = DEFAULT_XTB_CLIENT_ID,
) -> Path | None:
    candidates = []
    for path in sorted(Path(input_path).glob(f"xtb_*_{client_id}_*.xls*")):
        match = _CANONICAL_RE.fullmatch(path.name)
        if not match or match.group("client") != client_id:
            continue
        kind = match.group("kind")
        if required_kind not in kind.split("_"):
            continue
        start, end = extract_xtb_report_period(path)
        if end <= valuation_date:
            candidates.append((end, start, path))
    if not candidates:
        return None
    return sorted(candidates)[-1][2]


def read_xtb_sheet(path: Path, sheet_name: str) -> pd.DataFrame:
    with pd.ExcelFile(path) as workbook:
        header_row = detect_xtb_header_row(workbook, sheet_name)
        if header_row is None:
            return workbook.parse(sheet_name=sheet_name)
        return workbook.parse(sheet_name=sheet_name, header=header_row)


def read_xtb_open_positions(path: Path) -> pd.DataFrame:
    return read_xtb_sheet(path, XTB_SHEET_OPEN_POSITIONS)


def read_xtb_cash_operations(path: Path) -> pd.DataFrame:
    return read_xtb_sheet(path, XTB_SHEET_CASH_OPERATIONS)


def read_xtb_closed_positions(path: Path) -> pd.DataFrame:
    return read_xtb_sheet(path, XTB_SHEET_CLOSED_POSITIONS)


def xtb_open_position_rows(open_positions: pd.DataFrame) -> pd.DataFrame:
    if open_positions is None or open_positions.empty:
        return pd.DataFrame()
    df = open_positions.copy()
    if "Type" in df.columns:
        typed = df[df["Type"].notna() & df["Type"].astype(str).str.strip().ne("")]
        if not typed.empty:
            return typed.copy()
    if "Ticker" in df.columns:
        return df[df["Ticker"].notna() & df["Ticker"].astype(str).str.strip().ne("")].copy()
    return pd.DataFrame()


def xtb_open_positions_value(open_positions: pd.DataFrame) -> float:
    rows = xtb_open_position_rows(open_positions)
    if not rows.empty and "Value" in rows.columns:
        return float(pd.to_numeric(rows["Value"], errors="coerce").fillna(0.0).sum())
    return 0.0
