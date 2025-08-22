# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path
import pandas as pd

from m_bank_logs.data_model import MBANK_TRANSACTION_DATE, MBANK_OUTSTANDING_BALANCE
from m_bank_logs.read_m_transactions import read_m_transactions

#todo najpierw ustalmy wartość aktywów
#todo ustalić wartość lokat w mbank


def main(name):
    my_data_path = Path().home() / 'Dropbox' / 'INWESTYCJE' / 'assets'
    assert my_data_path.is_dir()

    static_data_path = Path(__file__).parent.parent / 'assets'
    assert static_data_path.is_dir()

    f = my_data_path / 'assets.xlsx'
    assert f.is_file()
    assets = pd.read_excel(f)


    df = read_m_transactions(my_data_path / 'm_23')
    last =df[-1:]
    for i, row in last.iterrows():
        d = {
            'id': 'm_23',
            'data wyceny': row[MBANK_TRANSACTION_DATE],
            'wartość': row[MBANK_OUTSTANDING_BALANCE],
        }
        break
    df_m_23 = pd.DataFrame(data=[d])

    assets = assets.merge(df_m_23, on='id', how='left')
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
