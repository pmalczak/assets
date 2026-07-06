# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

import pandas as pd

from main_proc.calculate_assets import calculate_assets
from importers.assets.data_model import AssetsDef

s = '________________________________________________\n'
col_space=15


def main():
    assets = calculate_assets(force_read_all_data=False)
    print(assets)
    print(s)
    assets.to_excel('assets_evaluation.xlsx', index=False)

    # rap3(assets)
    rap2(assets)
    rap1_prn(assets)
    return


def rap3(assets):
    msg = 'RAP 3___________________________________________'
    print(msg)
    a1 = assets[[AssetsDef.TYPE,
                 AssetsDef.CURRENCY,
                 AssetsDef.EVALUATION_DATE, AssetsDef.VALUE]]
    g1 = a1.groupby([
        AssetsDef.EVALUATION_DATE,
        AssetsDef.TYPE,
    ]).agg({
        AssetsDef.VALUE: 'sum',
        AssetsDef.CURRENCY: 'first',  # waluta taka jak w grupie
    })

    g1[AssetsDef.VALUE] = (
        g1[AssetsDef.VALUE]
        .round()
        .astype(int)
        .map('{:,}'.format)
        .str.replace(',', ' ')
    )

    g1[AssetsDef.VALUE] = g1[AssetsDef.VALUE] + ' ' + g1[AssetsDef.CURRENCY]
    g1 = g1.drop(columns=[AssetsDef.CURRENCY])
    print(g1.to_string(col_space=col_space))

    # print(g1)
    print(s)


def rap2(assets):
    msg = 'RAP 2___________________________________________'
    print(msg)
    # wybór kolumn
    a1 = assets[[
        AssetsDef.TYPE,
        AssetsDef.VALUE,
        AssetsDef.VALUE_PLN,
        AssetsDef.CURRENCY
    ]]

    # dodanie wierszy "Z RAZEM"
    a1_sum = a1.copy()
    a1_sum[AssetsDef.TYPE] = 'Z RAZEM'
    a1 = pd.concat([a1, a1_sum])

    # agregacja
    g1 = (
        a1
        .groupby([AssetsDef.TYPE, AssetsDef.CURRENCY])
        .sum()
        .round()
        .astype(int)
    )

    # pivot: waluta → kolumny
    g1 = g1.unstack(AssetsDef.CURRENCY)

    # spłaszczenie MultiIndex kolumn
    g1.columns = [
        f"{col}_{cur}".lower()
        for col, cur in g1.columns
    ]

    # formatowanie liczb
    for col in g1.columns:
        g1[col] = (
            g1[col]
            .map('{:,}'.format)
            .str.replace(',', ' ')
        )

    print(g1.to_string(col_space=col_space))
    print(s)


def rap2_0(assets):
    msg = 'RAP 2___________________________________________'
    print(msg)
    a1 = assets[[AssetsDef.TYPE,
                 # AssetsDef.EVALUATION_DATE,
                 AssetsDef.VALUE,
                 AssetsDef.VALUE_PLN,
                 AssetsDef.CURRENCY]]
    a1_g = a1.copy()
    a1_g[AssetsDef.TYPE] = 'Z RAZEM'
    a1 = pd.concat([a1, a1_g])

    g1 = a1.groupby([AssetsDef.CURRENCY, AssetsDef.TYPE]).sum().round().astype('int')
    g1[AssetsDef.VALUE] = g1[AssetsDef.VALUE].map('{:,}'.format).apply(lambda x: x.replace(',', ' '))
    g1[AssetsDef.VALUE] = g1[AssetsDef.VALUE] + ' ' + g1.index.get_level_values(AssetsDef.CURRENCY)
    g1[AssetsDef.VALUE_PLN] = g1[AssetsDef.VALUE_PLN].map('{:,}'.format).apply(lambda x: x.replace(',', ' '))
    print(g1.to_string(col_space=col_space))
    print(s)


def rap1_prn(assets):
    msg = 'RAP 1'
    print(msg)
    g1 = rap1(assets)
    print(g1.to_string(col_space=col_space))
    # print(s)


def rap1(assets: pd.DataFrame) -> pd.DataFrame:
    a1 = assets[[AssetsDef.GROUP, AssetsDef.CURRENCY, AssetsDef.VALUE_PLN]]
    a2 = a1.copy()
    a2[AssetsDef.GROUP] = 'Z RAZEM'
    a3 = a1.copy()
    a3[AssetsDef.CURRENCY] = 'RAZEM'
    a4 = a3.copy()
    a4[AssetsDef.GROUP] = 'Z RAZEM'

    # łączymy dane
    df = pd.concat([a1, a2, a3, a4])

    # grupowanie: GROUP + CURRENCY --> suma
    g1 = df.groupby([AssetsDef.GROUP, AssetsDef.CURRENCY]).sum()

    # pivot: waluty w kolumnach
    g1 = g1.unstack(AssetsDef.CURRENCY).fillna(0)

    # usuwamy MultiIndex kolumn po pivotowaniu
    g1.columns = g1.columns.get_level_values(1)

    # formatowanie kwot
    for col in g1.columns:
        g1[col] = (
            g1[col]
            .round()
            .astype(int)
            .map('{:,}'.format)
            .str.replace(',', ' ')
        )

    return g1


if __name__ == '__main__':
    pd.options.future.infer_string = True

    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 5000)
    pd.set_option('display.colheader_justify', 'center')

    main()
