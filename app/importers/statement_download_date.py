# -*- coding: utf-8 -*-
"""Data wyciągu = operacja pobrania pliku, nigdy data ostatniej transakcji."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path


def download_date_of(path: Path) -> date:
    """mtime pliku źródłowego (kiedy wyciąg wylądował na dysku)."""
    return datetime.fromtimestamp(path.stat().st_mtime).date()


def iso_download_date(path: Path) -> str:
    return download_date_of(path).isoformat()
