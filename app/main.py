# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path
import pandas as pd

from assets.data_model import AssetsFile, AssetsDef
from assets.read_assets import read_assets
from check_wrong_catalogs import check_wrong_catalogs
from data_root import get_online_data_root
from data_step.data_step import DATA_STEP
from evaluators.evaluate_assets import evaluate_assets


#todo najpierw ustalmy wartość aktywów
#todo ustalić wartość lokat w R


def main(name):
    local_data_steps_root = Path(__file__).parent.parent
    DATA_STEP.init_steps(root=local_data_steps_root)

    data_root = get_online_data_root()

    assets = read_assets()
    check_wrong_catalogs(data_root, assets)
    assets = evaluate_assets(data_root, assets)
    AssetsDef.check_structure(assets)

    assets = assets.sort_values(by=[AssetsFile.GROUP, AssetsFile.ID])
    assets = assets[assets[AssetsDef.VALUE] != 0]
    assets = assets.drop(columns=[AssetsDef.KIND, AssetsDef.NOTES])
    print(assets)

    a1 = assets[[AssetsDef.TYPE, AssetsDef.CURRENCY, AssetsDef.EVALUATION_DATE, AssetsDef.VALUE]]
    g1 = a1.groupby([AssetsDef.CURRENCY, AssetsDef.EVALUATION_DATE, AssetsDef.TYPE]).sum().round().astype('int')
    print_groupped_value(g1, AssetsDef.VALUE, AssetsDef.CURRENCY)

    a1 = assets[[AssetsDef.CURRENCY, AssetsDef.GROUP, AssetsDef.VALUE]]
    g1 = a1.groupby([AssetsDef.CURRENCY, AssetsDef.GROUP]).sum().round().astype('int')
    print_groupped_value(g1, AssetsDef.VALUE, AssetsDef.CURRENCY)
    return


def print_groupped_value(g1, value_column, currency_column):
    g1[value_column] = g1[value_column].map('{:,}'.format).apply(lambda x: x.replace(',', ' '))
    g1[value_column] = g1[value_column] + ' ' + g1.index.get_level_values(currency_column)
    print(g1)
    print()


if __name__ == '__main__':
    pd.options.mode.copy_on_write = True
    pd.options.future.infer_string = True

    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    pd.set_option('display.colheader_justify', 'center')
    main('PyCharm')
