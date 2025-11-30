# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from analyse_assets.select_asset import select_asset


def aquamarina(df: pd.DataFrame, fout: Path, result: dict) -> pd.DataFrame:
    m1 = (
            df["#Nadawca/Odbiorca"].str.contains("AQUAMARINA") |
            df["#Nadawca/Odbiorca"].str.contains("MIĘDZYZDROJE") |
            df["#Nadawca/Odbiorca"].str.contains("MARINA INVEST") #
    )
    m2 = df["#Numer konta"].str.contains("10124069600163204573190024")
    m3 = (
        df["#Tytuł"].str.contains("ZALICZKA DO ZLECENIA 20020793 ZA NAROŻNIK I MATERAC")
    )

    selector = m1 | m2
    return select_asset(df, selector, fout, result)


def _garaz(df: pd.DataFrame, fout: Path, result: dict) -> pd.DataFrame:
    m1 = (
         (df["#Nadawca/Odbiorca"].str.contains("IGLICA GARAŻ")) |
         (df["#Nadawca/Odbiorca"].str.contains("PODATEK GARAŻ"))
    )
    m2 = (
        (df["#Tytuł"].str.contains("GARAŻ") &
         (df["ROK"] >= 2020))
    )
    m3 = (
        (df["#Tytuł"] == 'OPŁATA ZA ZAKUP GARAŻU - UL. RUMIANKOWA')
    )

    selector = m1 | m2 | m3
    return select_asset(df, selector, fout, result)
