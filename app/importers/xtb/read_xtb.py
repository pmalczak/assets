# -*- coding: utf-8 -*-
from __future__ import annotations

from io import BytesIO
from datetime import date, timedelta
from pathlib import Path
import re
import zipfile

import pandas as pd

from data_step.data_step import DATA_STEP
from importers.xtb.data_model import (
    CASH_KIND,
    CLOSED_KIND,
    DEFAULT_XTB_CLIENT_ID,
    OPEN_KIND,
    XTB_SHEET_CASH_OPERATIONS,
    XTB_SHEET_CLOSED_POSITIONS,
    XTB_SHEET_OPEN_POSITIONS,
    XtbCashOperationsFile,
    XtbClosedPositionsFile,
    XtbExportSheetInfo,
    XtbOpenPositionsFile,
    is_xtb_cash_footer,
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
_SUMMARY_HEADERS = {"Product", "Metric", "Amount"}
_CASH_METRIC_TOKENS = ("free funds", "cash balance", "free cash")


def inspect_xtb_export(path: Path) -> list[XtbExportSheetInfo]:
    """Raportuje arkusze/kolumny eksportu XTB (ZIP/XLSX/CSV) bez zapisu do DATA_STEP."""
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


def _inspect_excel(buffer: BytesIO) -> list[XtbExportSheetInfo]:
    result = []
    with pd.ExcelFile(buffer) as workbook:
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
        values = _nonempty_values(row)
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
    required_kind: str = OPEN_KIND,
    client_id: str = DEFAULT_XTB_CLIENT_ID,
) -> Path | None:
    candidates = []
    for path in _iter_xtb_reports(input_path, required_kind, client_id):
        start, end = extract_xtb_report_period(path)
        if end <= valuation_date:
            candidates.append((end, start, path))
    if not candidates:
        return None
    return sorted(candidates)[-1][2]


def read_xtb_sheet(path: Path, sheet_name: str) -> pd.DataFrame:
    with pd.ExcelFile(path) as workbook:
        if sheet_name not in workbook.sheet_names:
            return pd.DataFrame()
        header_row = detect_xtb_header_row(workbook, sheet_name)
        if header_row is None:
            return workbook.parse(sheet_name=sheet_name)
        return workbook.parse(sheet_name=sheet_name, header=header_row)


def read_xtb_open(input_path: Path, asset_id: str) -> pd.DataFrame:
    resource = f"01 source/{asset_id}-open.parquet"
    r = DATA_STEP.obtain_dependent(resource, _read_xtb_open, input_path)
    return r.data_frame()


def read_xtb_closed(input_path: Path, asset_id: str) -> pd.DataFrame:
    resource = f"01 source/{asset_id}-closed.parquet"
    r = DATA_STEP.obtain_dependent(resource, _read_xtb_closed, input_path)
    return r.data_frame()


def read_xtb_cash(input_path: Path, asset_id: str) -> tuple[pd.DataFrame, list[str]]:
    resource = f"01 source/{asset_id}-cash.parquet"
    r = DATA_STEP.obtain_dependent(resource, _read_xtb_cash, input_path)
    warnings = period_gap_warnings(_named_periods(input_path, CASH_KIND), CASH_KIND)
    return r.data_frame(), warnings


def latest_open_as_of(open_df: pd.DataFrame, valuation_date: date) -> pd.DataFrame:
    if open_df is None or open_df.empty:
        return pd.DataFrame(columns=list(XtbOpenPositionsFile.expected_columns()))
    end_dates = pd.to_datetime(open_df[XtbOpenPositionsFile.PERIOD_END], errors="coerce").dt.date
    eligible = open_df.loc[end_dates <= valuation_date].copy()
    if eligible.empty:
        return eligible
    latest_end = eligible[XtbOpenPositionsFile.PERIOD_END].max()
    return eligible.loc[eligible[XtbOpenPositionsFile.PERIOD_END] == latest_end].copy()


def period_gap_warnings(periods: list[tuple[date, date]], label: str) -> list[str]:
    if len(periods) <= 1:
        return []
    ordered = sorted(periods)
    warnings = []
    for prev, nxt in zip(ordered, ordered[1:]):
        gap_start = prev[1] + timedelta(days=1)
        gap_end = nxt[0] - timedelta(days=1)
        if gap_start <= gap_end:
            warnings.append(
                f"Luka w okresach XTB {label}: {gap_start.isoformat()} … {gap_end.isoformat()}"
            )
    return warnings


def xtb_open_position_rows(open_positions: pd.DataFrame) -> pd.DataFrame:
    if open_positions is None or open_positions.empty:
        return pd.DataFrame(columns=list(XtbOpenPositionsFile.expected_columns()))
    if XtbOpenPositionsFile.TICKER not in open_positions.columns:
        return pd.DataFrame(columns=list(XtbOpenPositionsFile.expected_columns()))
    ticker = open_positions[XtbOpenPositionsFile.TICKER]
    rows = open_positions.loc[ticker.notna() & ticker.astype(str).str.strip().ne("")].copy()
    return drop_xtb_instrument_aggregates(rows)


def drop_xtb_instrument_aggregates(rows: pd.DataFrame) -> pd.DataFrame:
    """Open Positions: wiersz instrumentu (Type puste) + loty (Type=BUY/SELL).

    Agregat powiela Value/Volume lotów — zostawiamy loty; wiersz instrumentu tylko
    gdy dla tickera nie ma lotu (uproszczone eksporty / testy).
    """
    if rows is None or rows.empty or XtbOpenPositionsFile.TYPE not in rows.columns:
        return rows
    is_lot = rows[XtbOpenPositionsFile.TYPE].map(_is_xtb_open_lot_type)
    if not bool(is_lot.any()):
        return rows
    ticker = rows[XtbOpenPositionsFile.TICKER].map(lambda value: str(value or "").strip())
    lot_tickers = set(ticker[is_lot])
    return rows.loc[is_lot | ~ticker.isin(lot_tickers)].copy()


def _is_xtb_open_lot_type(value) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    text = str(value).strip().lower()
    if not text or text in {"nan", "none"}:
        return False
    return text.startswith("buy") or text.startswith("sell")


def xtb_cash_rows(open_positions: pd.DataFrame) -> pd.DataFrame:
    if open_positions is None or open_positions.empty:
        return pd.DataFrame(columns=list(XtbOpenPositionsFile.expected_columns()))
    if XtbOpenPositionsFile.TICKER not in open_positions.columns:
        return pd.DataFrame(columns=list(XtbOpenPositionsFile.expected_columns()))
    ticker = open_positions[XtbOpenPositionsFile.TICKER]
    return open_positions.loc[ticker.isna() | ticker.astype(str).str.strip().eq("")].copy()


def xtb_open_positions_value(open_positions: pd.DataFrame) -> float:
    if open_positions is None or open_positions.empty:
        return 0.0
    if XtbOpenPositionsFile.VALUE not in open_positions.columns:
        return 0.0
    return float(pd.to_numeric(open_positions[XtbOpenPositionsFile.VALUE], errors="coerce").fillna(0.0).sum())


def parse_xtb_number(value) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return None
    s = s.replace("\xa0", "").replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    s = re.sub(r"[^\d.\-]", "", s)
    if s in ("", "-", ".", "-."):
        return None
    return float(s)


def parse_xtb_date(value) -> date | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.date()


def _read_xtb_open(source_file: Path = None) -> pd.DataFrame:
    return _read_many(source_file, OPEN_KIND, _parse_open_file, XtbOpenPositionsFile)


def _read_xtb_closed(source_file: Path = None) -> pd.DataFrame:
    result = _read_many(source_file, CLOSED_KIND, _parse_closed_file, XtbClosedPositionsFile)
    if result.empty:
        return result
    result = result.drop_duplicates(subset=XtbClosedPositionsFile.unique_key(), keep="last")
    return _sort_by_optional_date(result, XtbClosedPositionsFile.CLOSE_TIME)


def _read_xtb_cash(source_file: Path = None) -> pd.DataFrame:
    result = _read_many(source_file, CASH_KIND, _parse_cash_file, XtbCashOperationsFile)
    if result.empty:
        return result
    result = result.drop_duplicates(subset=XtbCashOperationsFile.unique_key(), keep="last")
    return _sort_by_optional_date(result, XtbCashOperationsFile.TIME)


def _read_many(source_file: Path, required_kind: str, reader, model) -> pd.DataFrame:
    input_files = _iter_xtb_reports(source_file, required_kind)
    empty = pd.DataFrame(columns=list(model.expected_columns()))
    if not input_files:
        return empty

    records = []
    for input_file in input_files:
        start, end = extract_xtb_report_period(input_file)
        df = reader(input_file)
        df[model.PERIOD_START] = start.isoformat()
        df[model.PERIOD_END] = end.isoformat()
        df[model.FILE_DATE] = end.isoformat()
        print(f"PLIK:{input_file} {len(df):>4} rekord/ów (XTB {required_kind})")
        records.append(df)

    result = pd.concat(records, ignore_index=True)
    model.check_structure(result)
    return result


def _parse_open_file(path: Path) -> pd.DataFrame:
    raw = read_xtb_sheet(path, XTB_SHEET_OPEN_POSITIONS)
    positions = _normalize_open(raw)
    cash = _cash_rows_from_open_summary(path)
    frames = [frame for frame in (positions, cash) if frame is not None and not frame.empty]
    if not frames:
        return _empty_without_period(XtbOpenPositionsFile)
    return pd.concat(frames, ignore_index=True)


def _parse_closed_file(path: Path) -> pd.DataFrame:
    return _normalize_closed(read_xtb_sheet(path, XTB_SHEET_CLOSED_POSITIONS))


def _parse_cash_file(path: Path) -> pd.DataFrame:
    return _normalize_cash(read_xtb_sheet(path, XTB_SHEET_CASH_OPERATIONS))


def _normalize_open(df: pd.DataFrame) -> pd.DataFrame:
    out = _ensure_columns(df, XtbOpenPositionsFile)
    ticker = out[XtbOpenPositionsFile.TICKER].astype(str).str.strip()
    out = out.loc[ticker.ne("") & ticker.str.lower().ne("nan")].copy()
    for col in (XtbOpenPositionsFile.VOLUME, XtbOpenPositionsFile.VALUE):
        out[col] = out[col].map(parse_xtb_number)
    return drop_xtb_instrument_aggregates(out)


def _normalize_closed(df: pd.DataFrame) -> pd.DataFrame:
    out = _ensure_columns(df, XtbClosedPositionsFile)
    for col in (
        XtbClosedPositionsFile.VOLUME,
        XtbClosedPositionsFile.OPEN_PRICE,
        XtbClosedPositionsFile.CLOSE_PRICE,
        XtbClosedPositionsFile.PROFIT,
    ):
        out[col] = out[col].map(parse_xtb_number)
    return out


def _normalize_cash(df: pd.DataFrame) -> pd.DataFrame:
    out = _ensure_columns(df, XtbCashOperationsFile)
    if not out.empty:
        footer = out[XtbCashOperationsFile.TYPE].map(is_xtb_cash_footer)
        out = out.loc[~footer].copy()
    for col in (XtbCashOperationsFile.AMOUNT, XtbCashOperationsFile.BALANCE):
        if col in out.columns:
            out[col] = out[col].map(parse_xtb_number)
    return out


def _ensure_columns(df: pd.DataFrame, model) -> pd.DataFrame:
    period_cols = {model.FILE_DATE, model.PERIOD_START, model.PERIOD_END}
    expected = list(model.expected_columns() - period_cols)
    if df is None or df.empty:
        return pd.DataFrame(columns=expected)
    out = df.copy()
    out.columns = [str(col).strip() for col in out.columns]
    for col in expected:
        if col not in out.columns:
            out[col] = ""
    out = out[expected]
    numeric = {
        XtbOpenPositionsFile.VOLUME,
        XtbOpenPositionsFile.VALUE,
        XtbClosedPositionsFile.VOLUME,
        XtbClosedPositionsFile.OPEN_PRICE,
        XtbClosedPositionsFile.CLOSE_PRICE,
        XtbClosedPositionsFile.PROFIT,
        XtbCashOperationsFile.AMOUNT,
        XtbCashOperationsFile.BALANCE,
    }
    for col in expected:
        if col in numeric:
            continue
        # Excel: puste ID → float NaN, wypełnione → float/int; parquet nie znosi mieszanego object.
        out[col] = out[col].map(_cell_str)
    return out


def _empty_without_period(model) -> pd.DataFrame:
    period_cols = {model.FILE_DATE, model.PERIOD_START, model.PERIOD_END}
    return pd.DataFrame(columns=list(model.expected_columns() - period_cols))


def _cash_rows_from_open_summary(path: Path) -> pd.DataFrame:
    rows = []
    with pd.ExcelFile(path) as workbook:
        if XTB_SHEET_OPEN_POSITIONS not in workbook.sheet_names:
            return _empty_without_period(XtbOpenPositionsFile)
        preview = workbook.parse(sheet_name=XTB_SHEET_OPEN_POSITIONS, header=None, nrows=40)
        header_idx = None
        for idx, row in preview.iterrows():
            if _SUMMARY_HEADERS <= _nonempty_values(row):
                header_idx = int(idx)
                break
        if header_idx is None:
            return _empty_without_period(XtbOpenPositionsFile)

        header = [_cell_str(value) or f"c{i}" for i, value in enumerate(preview.iloc[header_idx].tolist())]
        for _, row in preview.iloc[header_idx + 1 :].iterrows():
            mapped = {_cell_str(header[i]) if i < len(header) else f"c{i}": value for i, value in enumerate(row.tolist())}
            product = _cell_str(mapped.get("Product"))
            metric = _cell_str(mapped.get("Metric"))
            if not product and not metric:
                continue
            if {"Instrument/Position", "Ticker", "Volume"} <= {str(v).strip() for v in mapped.values() if v is not None}:
                break
            if not _is_cash_metric(metric, product):
                continue
            amount = parse_xtb_number(mapped.get("Amount"))
            if amount is None:
                continue
            rows.append(
                {
                    XtbOpenPositionsFile.PRODUCT: product or "Cash",
                    XtbOpenPositionsFile.INSTRUMENT: metric or "Free funds",
                    XtbOpenPositionsFile.TICKER: "",
                    XtbOpenPositionsFile.ISIN: "",
                    XtbOpenPositionsFile.VOLUME: None,
                    XtbOpenPositionsFile.VALUE: amount,
                    XtbOpenPositionsFile.CURRENCY: _cell_str(mapped.get("Currency")),
                    XtbOpenPositionsFile.TYPE: "CASH",
                    XtbOpenPositionsFile.POSITION_ID: "",
                }
            )
    if not rows:
        return _empty_without_period(XtbOpenPositionsFile)
    result = pd.DataFrame(rows)
    return _ensure_columns(result, XtbOpenPositionsFile)


def _is_cash_metric(metric: str, product: str) -> bool:
    blob = f"{metric} {product}".strip().lower()
    if not blob:
        return False
    if "profit" in blob:
        return False
    if any(token in blob for token in _CASH_METRIC_TOKENS):
        return True
    return blob == "cash" or product.strip().lower() == "cash"


def _iter_xtb_reports(
    source_dir: Path,
    required_kind: str,
    client_id: str = DEFAULT_XTB_CLIENT_ID,
) -> list[Path]:
    if source_dir is None:
        return []
    root = Path(source_dir)
    if not root.is_dir():
        return []
    paths = []
    for path in sorted(list(root.glob(f"xtb_*_{client_id}_*.xls*")) + list(root.glob(f"xtb_*_{client_id}_*.csv"))):
        match = _CANONICAL_RE.fullmatch(path.name)
        if not match or match.group("client") != client_id:
            continue
        kind = match.group("kind")
        if required_kind not in kind.split("_"):
            continue
        paths.append(path)
    return paths


def _named_periods(
    source_dir: Path,
    required_kind: str,
    client_id: str = DEFAULT_XTB_CLIENT_ID,
) -> list[tuple[date, date]]:
    return [extract_xtb_report_period(path) for path in _iter_xtb_reports(source_dir, required_kind, client_id)]


def _sort_by_optional_date(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    if df.empty or date_col not in df.columns:
        return df.reset_index(drop=True)
    out = df.copy()
    out["_sort"] = out[date_col].map(lambda value: parse_xtb_date(value) or date.min)
    out = out.sort_values("_sort").drop(columns=["_sort"]).reset_index(drop=True)
    return out


def _nonempty_values(row: pd.Series) -> set[str]:
    return {
        str(value).strip()
        for value in row.tolist()
        if value is not None and not pd.isna(value) and str(value).strip()
    }


def _cell_str(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        number = float(value)
        if number.is_integer():
            return str(int(number))
        return str(value).strip()
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none"} else text
