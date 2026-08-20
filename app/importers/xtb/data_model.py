# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_XTB_ASSET_ID = "p_xtb"
DEFAULT_XTB_CLIENT_ID = "55260027"
XTB_FILE_PREFIX = "xtb"

XTB_SHEET_OPEN_POSITIONS = "Open Positions"
XTB_SHEET_CLOSED_POSITIONS = "Closed Positions"
XTB_SHEET_CASH_OPERATIONS = "Cash Operations"


@dataclass(frozen=True)
class XtbExportSheetInfo:
    sheet_name: str
    columns: tuple[str, ...]
    rows: int
    header_row: int | None = None
