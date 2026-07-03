# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"
import pandas as pd

from analyse_assets.data_model import AssetRw
from analyse_assets.select_asset import select_asset


def karpacz(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    df, r1 = select_asset(df, (
        (df[AssetRw.MBANK_ACCOUNT_NUMBER] == "87114020040000330286652080")
        ),
            AssetRw.initial_investment_mapping)

    # df, r2 = select_asset(df, (
    #         (df[AssetRw.MBANK_TITLE] == "DAROWIZNA")
    #         & (df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("KRYSTYNA MALCZAK"))
    #         & (df[AssetRw.YEAR] == "2022")
    #         & (df[AssetRw.MBANK_AMOUNT] > 0)
    #         ),
    #         AssetRw.investment_refund_mapping)

    df, r3 = select_asset(df, (
        (df[AssetRw.MBANK_ACCOUNT_NUMBER] == "39105017511000009755659050") # notariusz
        | (df[AssetRw.MBANK_ACCOUNT_NUMBER] == '52105000997198105701000230') # czynsz
        ),
        AssetRw.inflow_outflow_mapping)

    # df, r4 = select_asset(df, (
    #     df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("PODATEK OPOCZYŃSKA")
    #     | df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("ZAUŁEK ZŁOTNICKI III")
    #     | df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("MOICO")
    #     | df[AssetRw.MBANK_TITLE].str.contains("ZWROT ZA RACHUNKI")
    #     | df[AssetRw.MBANK_TITLE].str.contains("ZWROT ZA R-KI")
    #     ),
    #     AssetRw.inflow_outflow_mapping)

    r = pd.concat([r1,
                   # r2,
                   r3,
                   # r4,
                   ])
    return df, r
