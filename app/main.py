# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path
import pandas as pd

from assets.read_assets import read_assets
from check_wrong_catalogs import check_wrong_catalogs
from data_step.data_step import DATA_STEP
from assets.evaluate_assets import evaluate_assets
from mbank_importer.evaluate_mbank_deposit import evaluate_mbank_deposits


#todo najpierw ustalmy wartość aktywów
#todo ustalić wartość lokat w R


def evaluate_deposits(data_root, assets):
    _assets = assets['typ'] == 'ror'
    _assets = assets[_assets]

    result = []
    for i, rec in _assets.iterrows():
        a = rec['id']
        waluta = rec['waluta']
        r = evaluate_mbank_deposits(data_root, a, waluta)
        if len(r) > 0:
            result += [r]

    result = pd.concat(result)

    return result


def main(name):
    proj_root = Path(__file__).parent.parent
    DATA_STEP.init_steps(root=proj_root)

    data_root = Path().home() / 'Dropbox' / 'INWESTYCJE' / 'assets'
    assert data_root.is_dir()

    assets = read_assets(data_root)
    check_wrong_catalogs(data_root, assets)
    assets_valuation = evaluate_assets(data_root, assets)

    assets = assets.merge(assets_valuation, on='id', how='left')

    deposits_valuation = evaluate_deposits(data_root, assets)
    assets = pd.concat([assets, deposits_valuation])
    assets = assets.sort_values(by=['grupa', 'id'])

    assets = assets[assets['wartość'] != 0]
    print(assets)

    a1 = assets[['opis', 'waluta', 'wartość']]
    g1 = a1.groupby(['waluta', 'opis']).sum().round().astype('int')
    print(g1)
    return


if __name__ == '__main__':
    pd.options.mode.copy_on_write = True
    pd.options.future.infer_string = True

    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    pd.set_option('display.colheader_justify', 'center')
    main('PyCharm')
