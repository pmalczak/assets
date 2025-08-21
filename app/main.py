# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path
import pandas as pd


def main(name):
    my_data_path = Path().home() / 'Dropbox' / 'INWESTYCJE' / 'assets'
    assert my_data_path.is_dir()

    static_data_path = Path(__file__).parent.parent / 'assets'
    assert static_data_path.is_dir()

    f = my_data_path / 'assets.xlsx'
    assert f.is_file()
    assets = pd.read_excel(f)

    print(assets)
    return


if __name__ == '__main__':
    pd.options.mode.copy_on_write = True
    pd.options.future.infer_string = True

    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    pd.set_option('display.colheader_justify', 'center')

    main('PyCharm')
