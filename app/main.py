# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path
import pandas as pd

from assets.data_model import AssetsFile, AssetsDef
from assets.read_assets import read_assets
from check_wrong_catalogs import check_wrong_catalogs
from data_step.data_step import DATA_STEP
from evaluators.evaluate_assets import evaluate_assets
from int_formatter import int_formatter


#todo najpierw ustalmy wartość aktywów
#todo ustalić wartość lokat w R


def main(name):
    proj_root = Path(__file__).parent.parent
    DATA_STEP.init_steps(root=proj_root)

    data_root = Path().home() / 'Dropbox' / 'INWESTYCJE' / 'assets'
    assert data_root.is_dir()

    assets = read_assets(data_root)
    check_wrong_catalogs(data_root, assets)
    assets = evaluate_assets(data_root, assets)
    AssetsDef.check_structure(assets)

    assets = assets.sort_values(by=[AssetsFile.GROUP, AssetsFile.ID])
    assets = assets[assets[AssetsDef.VALUE] != 0]
    assets = assets.drop(columns=['rodzaj', 'dostęp'])
    print(assets)

    a1 = assets[[AssetsDef.TYPE, AssetsDef.CURRENCY, AssetsDef.EVALUATION_DATE, AssetsDef.VALUE]]
    g1 = a1.groupby([AssetsDef.CURRENCY, AssetsDef.EVALUATION_DATE, AssetsDef.TYPE]).sum().round().astype('int')
    print(int_formatter(g1))

    a1 = assets[['waluta', 'grupa', 'wartość']]
    g1 = a1.groupby(['waluta', 'grupa']).sum().round().astype('int')
    print(int_formatter(g1))

    return


if __name__ == '__main__':
    pd.options.mode.copy_on_write = True
    pd.options.future.infer_string = True

    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    pd.set_option('display.colheader_justify', 'center')
    main('PyCharm')
