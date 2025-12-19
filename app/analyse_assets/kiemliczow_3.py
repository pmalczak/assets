# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"
import pandas as pd

from analyse_assets.data_model import AssetRw
from analyse_assets.select_asset import select_asset


def kiemliczow_3(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    r0 = AssetRw.create([
        ('2012-05-28', -7290.0, AssetRw.CAT_OUTFLOW, 'OPŁATA NOTARIALNA I PODATKI / GOTÓWKA'),
        ('2012-05-28', -200.0, AssetRw.CAT_OUTFLOW, 'WYPIS Z KW / GOTÓWKA'),
        ('2012-06-13', -1904.29, AssetRw.CAT_OUTFLOW, 'ZAKUP OKIEN DO MIESZK B.JASI / GOTÓWKA'),
        ]
    )
    df, r1 = select_asset(df, (
            df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("GRZEGORZ KOPACKI") |
            df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("GRZEGORZ I AGATA KOPACCY")
            ), AssetRw.initial_investment_mapping)

    df, r2 = select_asset(df, (
            (df[AssetRw.MBANK_TITLE].str.contains("KIEMLICZÓW 9/3")
                | df[AssetRw.MBANK_TRANSACTION_PARTY].str
                    .contains("WOJCIECH GOŁĘBIOWSKI  UL.ŚCIEGIENNEGO 69 M.38            30-809 KRAKÓW"))

            | (df[AssetRw.MBANK_TITLE].str.contains("ROZLICZENIE KAUCJI")
               | df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("GOŁĘBIOWSKI"))

            | (df[AssetRw.MBANK_TITLE].str.contains("CZYNSZ")
               & df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("RUSLAN KOSSAK"))

            | (df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("KRZYSZTOF TUTAJ"))
            | (df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("STANISŁAW EDMUND TUTAJ"))
            | (df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("STANISŁAW TUTAJ"))
            ), AssetRw.inflow_outflow_mapping)

    r = pd.concat([r0, r1, r2])
    return df, r
