# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from analyse_assets.select_asset import select_asset


def kiemliczow_1(df: pd.DataFrame, fout: Path, result: dict) -> pd.DataFrame:
    m1 = (
        (df["#Numer konta"] == "20102052420000250201100809")
        | (df["#Numer konta"] == "20102052420000250201100809")
    )

    selector = m1
    return select_asset(df, selector, fout, result)
