# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path
import pandas as pd

from evaluate_assets import evaluate_assets

#todo najpierw ustalmy wartość aktywów
#todo ustalić wartość lokat w mbank
#todo ustalić wartość lokat w R


def check_wrong_catalogs(my_data_path: Path, assets: pd.DataFrame):
    # todo sprawdzić strukturę katalogów w assets tj. pokazać martwe katalogi
    return


def main(name):
    my_data_path = Path().home() / 'Dropbox' / 'INWESTYCJE' / 'assets'
    assert my_data_path.is_dir()

    # static_data_path = Path(__file__).parent.parent / 'assets'
    # assert static_data_path.is_dir()

    f = my_data_path / 'assets.xlsx'
    assert f.is_file()
    assets = pd.read_excel(f)

    check_wrong_catalogs(my_data_path, assets)

    assets_valuation = evaluate_assets(my_data_path, assets)

    assets = assets.merge(assets_valuation, on='id', how='left')
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
