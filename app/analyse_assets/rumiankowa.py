# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"
from pathlib import Path
import pandas as pd
from analyse_assets.select_asset import select_asset, print_asset
from analyse_assets.data_model import AssetRw


def rumiankowa(df: pd.DataFrame, fout: Path, result: dict) -> pd.DataFrame:
    m = (
        (df[AssetRw.MBANK_ACCOUNT_NUMBER] == "26234000091290401000003553") # raiffeisen kredyt hipo
        | (df[AssetRw.MBANK_ACCOUNT_NUMBER] == "77249000050000400032972350")  # Katarzyna Żaczek
    )
    df, r1 = select_asset(df, m, AssetRw.inflow_outflow_mapping)
    m = (
        df[AssetRw.MBANK_TITLE].str.contains("WKŁAD WŁASNY NA POCZET ZAKUPU MIESZKANIA UL. RUMIANKOWA 57D/4 WROCŁAW")
        | df[AssetRw.MBANK_TITLE].str.contains("ZAKUP LOKALU MIESZKALNEGO NR 4, WROCŁAW, UL. RUMIANKOWA 57D, REP A 1684/2019")
        | df[AssetRw.MBANK_TITLE].str.contains("DEC.129/2017; RUMIANKOWA 57D/4PRZEKSZ. UŻ WIECZ W PRAWO WŁ")
    )
    df, r2 = select_asset(df, m, AssetRw.inflow_outflow_mapping)
    m = (
        (df[AssetRw.MBANK_TITLE].str.contains("RUMIANKOWA 57D") & df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("IGLICA"))
        | (df[AssetRw.MBANK_TITLE].str.contains("PRZEKSIĘGOWANIE NADWYŻKI PO SPŁACIEKREDYTU") &
           df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("RAIFFEISEN BANK INT. AG"))
    )
    df, r3 = select_asset(df, m, AssetRw.inflow_outflow_mapping)
    m = (
        (df[AssetRw.MBANK_TITLE].str.contains("WYNAJEM LOKALU") & df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("GPM SYSTEMY"))
        | (df[AssetRw.MBANK_TITLE].str.contains("RACH") & (df["#Kwota"] == 2200.0))
        | (df[AssetRw.MBANK_TITLE].str.contains("RACH") & (df["#Kwota"] == 2750.0))
        | (df[AssetRw.MBANK_TITLE].str.contains("RACH") & (df["#Kwota"] == 250.0))
    )
    df, r4 = select_asset(df, m, AssetRw.inflow_outflow_mapping)

    r = pd.concat([r1, r2, r3, r4])
    print_asset(r, fout, result)
    return df
