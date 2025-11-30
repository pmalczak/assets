# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from analyse_assets.select_asset import select_asset


def rumiankowa(df: pd.DataFrame, fout: Path, result: dict) -> pd.DataFrame:
    m1 = (
        (df["#Numer konta"] == "26234000091290401000003553") # raiffeisen kredyt hipo
        | (df["#Numer konta"] == "77249000050000400032972350")  # Katarzyna Żaczek
    )
    m2 = (
        df["#Tytuł"].str.contains("WKŁAD WŁASNY NA POCZET ZAKUPU MIESZKANIA UL. RUMIANKOWA 57D/4 WROCŁAW")
        | df["#Tytuł"].str.contains("ZAKUP LOKALU MIESZKALNEGO NR 4, WROCŁAW, UL. RUMIANKOWA 57D, REP A 1684/2019")
        | df["#Tytuł"].str.contains("DEC.129/2017; RUMIANKOWA 57D/4PRZEKSZ. UŻ WIECZ W PRAWO WŁ")
    )
    m3 = (
        (df["#Tytuł"].str.contains("RUMIANKOWA 57D") & df["#Nadawca/Odbiorca"].str.contains("IGLICA"))
        | (df["#Tytuł"].str.contains("PRZEKSIĘGOWANIE NADWYŻKI PO SPŁACIEKREDYTU") &
           df["#Nadawca/Odbiorca"].str.contains("RAIFFEISEN BANK INT. AG"))
    )
    m4 = (
        (df["#Tytuł"].str.contains("WYNAJEM LOKALU") & df["#Nadawca/Odbiorca"].str.contains("GPM SYSTEMY"))
        | (df["#Tytuł"].str.contains("RACH") & (df["#Kwota"] == 2200.0))
        | (df["#Tytuł"].str.contains("RACH") & (df["#Kwota"] == 2750.0))
        | (df["#Tytuł"].str.contains("RACH") & (df["#Kwota"] == 250.0))
    )

    selector = m1 | m2 | m3 | m4
    return select_asset(df, selector, fout, result)
