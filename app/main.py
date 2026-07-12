# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from datetime import date

import pandas as pd

from asset_reports import rap1, rap2
from main_proc.calculate_assets import calculate_assets
from importers.assets.data_model import AssetsDef

s = '________________________________________________\n'
col_space=15


def main():
    valuation_date = date.today()

    assets = calculate_assets(valuation_date=valuation_date, force_read_all_data=False)
    print(assets)
    print(s)
    assets.to_excel(f'assets_evaluation_{valuation_date}.xlsx', index=False)

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


def rap1_prn(assets):
    msg = 'RAP 1'
    print(msg)
    g1 = rap1(assets)
    print(g1.to_string(col_space=col_space))
    # print(s)


if __name__ == '__main__':
    pd.options.future.infer_string = True

    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 5000)
    pd.set_option('display.colheader_justify', 'center')

    main()
