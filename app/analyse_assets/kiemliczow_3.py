# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from analyse_assets.data_model import AssetRw
from analyse_assets.select_asset import select_asset


def kiemliczow_3(df: pd.DataFrame, fout: Path, result: dict) -> pd.DataFrame:
    m1 = (
            df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("GRZEGORZ KOPACKI") |
            df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("GRZEGORZ I AGATA KOPACCY")
    )
    m2 = (
        df[AssetRw.MBANK_TITLE].str.contains("DEPOZYT DO UMOWY SPRZEDAŻY STAROGAJOWA 23")
        | df[AssetRw.MBANK_TITLE].str.contains("KIEMLICZÓW 9/3")
    )

    selector = m1 | m2
    return select_asset(df, selector, fout, result)
