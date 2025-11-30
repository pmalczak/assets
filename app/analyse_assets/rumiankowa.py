# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from analyse_assets.select_asset import select_asset


def rumiankowa(df: pd.DataFrame, fout: Path, result: dict) -> pd.DataFrame:
    m1 = (
        df["#Numer konta"] == "26234000091290401000003553" # raiffeisen kredyt hipo
    )
    m2 = (
        df["#Tytuł"].str.contains("WKŁAD WŁASNY NA POCZET ZAKUPU MIESZKANIA UL. RUMIANKOWA 57D/4 WROCŁAW")
        | df["#Tytuł"].str.contains("ZAKUP LOKALU MIESZKALNEGO NR 4, WROCŁAW, UL. RUMIANKOWA 57D, REP A 1684/2019")
    )

    selector = m1 | m2
    return select_asset(df, selector, fout, result)
