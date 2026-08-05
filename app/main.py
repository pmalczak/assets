# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from datetime import date

import pandas as pd

from asset_reports import rap1, rap2
from app_proc.calculate_assets import calculate_assets

s = '________________________________________________\n'
col_space=15


def main():
    valuation_date = date.today()

    assets = calculate_assets(valuation_date=valuation_date, force_read_all_data=False)
    print(assets)
    print(s)

    rap2(assets)
    rap1_prn(assets)
    return


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
