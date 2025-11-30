# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from analyse_assets.select_asset import select_asset


def horbaczewskiego(df: pd.DataFrame, fout: Path, result: dict) -> pd.DataFrame:
    #
    m1   = (
        (df["#Numer konta"] == "07124067263111001055248115") # PEKAOSA - ARKADIUSZ GĄCIARZ KREDYT
        | (df["#Numer konta"] == "33124067261111001052301556")  # ARKADIUSZ GĄCIARZ -ROR
    )
    m2 = (
            df["#Numer konta"] == "28114020040000390279513454"
    )
    m3 = (
        (df["#Tytuł"].str.contains("DEPOZYT NOTARIALNY") &
         df["#Nadawca/Odbiorca"].str.contains("KANCELARIA NOTARIALNA NATALIA ŁYSZCZAK ANNA PIKUŁA-SZUBA")) |

        (df["#Tytuł"].str.contains("ZALICZKA MIESZKANIE") &
         df["#Nadawca/Odbiorca"].str.contains("BEDEKIER JACEK STANISŁAW           I BEDEKIER JUSTYNA"))
    )

    selector = m1 | m2 | m3
    return select_asset(df, selector, fout, result)
