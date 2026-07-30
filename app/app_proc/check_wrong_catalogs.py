# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from app_proc.data_root import get_cash_pool_root
from importers.assets.read_assets import ASSETS_FILE_NAME


def check_wrong_catalogs(data_root: Path, assets: pd.DataFrame):
    """Raportuje katalogi w assets/ i cash_pool/ nieobecne w assets_1.xlsx."""
    roots = [data_root]
    cash_pool = get_cash_pool_root()
    if cash_pool.is_dir() and cash_pool.resolve() != Path(data_root).resolve():
        roots.append(cash_pool)

    dir_names: list[str] = []
    for root in roots:
        dir_names.extend(p.name for p in root.glob("*") if p.is_dir())

    dirs = pd.DataFrame({"id": dir_names})
    _assets = assets.copy()
    _assets["x"] = 1
    result = dirs.merge(_assets, on="id", how="left")
    result = result[result["x"].isnull()]
    result = result[["id"]].rename(
        columns={"id": f'nadmiarowe katalogi nieujawnione w "{ASSETS_FILE_NAME}"'}
    )
    if not result.empty:
        print(result)
    return
