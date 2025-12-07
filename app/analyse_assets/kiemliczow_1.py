# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"
import pandas as pd

from analyse_assets.data_model import AssetRw


def kiemliczow_1(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    r0 = AssetRw.create([
        ('1997-06-02', -48600.0, AssetRw.CAT_INVESTMENT, 'zakup mieszkania [54m2]'),
        ('2000-01-03', 156600.0, AssetRw.CAT_CLOSING, 'sprzedaż'),
        ('2000-04-04', -3700.0, AssetRw.CAT_OUTFLOW, 'opłata skarbowa'),
        ('2000-04-04', -695.5, AssetRw.CAT_OUTFLOW, 'prowizja'),
        ('2001-08-20', -572.5, AssetRw.CAT_OUTFLOW, 'hipoteka - opłata sądowa'),
        ('2001-10-05', -145.0, AssetRw.CAT_OUTFLOW, 'hipoteka - opłata sądowa'),
    ])
    return df, r0
