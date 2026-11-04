# -*- coding: utf-8 -*-
"""Hard-fail resolver katalogu aktywa / brokera (brak wiersza assets lub katalogu → ValueError)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from app_proc.data_root import resolve_asset_dir
from importers.assets.data_model import AssetsDef
from importers.assets.read_assets import read_assets


def require_asset_dir(asset_id: str, typ: str) -> Path:
    """``resolve_asset_dir`` + twardy błąd, gdy katalog nie istnieje."""
    asset_dir = resolve_asset_dir(asset_id, typ)
    if not Path(asset_dir).is_dir():
        raise ValueError(f"Brak katalogu: {asset_dir}")
    return Path(asset_dir)


def require_broker_asset_dir(
    broker_id: str,
    *,
    assets: pd.DataFrame | None = None,
) -> Path:
    """Katalog brokera z wiersza ``assets``; brak ID lub katalogu → ``ValueError``."""
    frame = assets if assets is not None else read_assets()
    rows = frame[frame[AssetsDef.ID].astype(str) == broker_id]
    if rows.empty:
        raise ValueError(
            f"Brak aktywa brokerskiego {broker_id!r} w a_config.xlsx (arkusz assets)"
        )
    row = rows.iloc[0]
    return require_asset_dir(broker_id, row[AssetsDef.TYPE])
