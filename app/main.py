# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path
import pandas as pd

from assest.read_assets import read_assets
from check_wrong_catalogs import check_wrong_catalogs
from data_step.data_step import DATA_STEP
from assest.evaluate_assets import evaluate_assets
from mbank_logs.data_model import MBANK_DESCRIPTION, MBANK_TITLE, MbankOperationType, MBANK_AMOUNT
from mbank_logs.read_m_transactions import read_m_transactions


#todo najpierw ustalmy wartość aktywów
#todo ustalić wartość lokat w mbank
#todo ustalić wartość lokat w R


def evaluate_deposits(data_root, assets):
    result = evaluate_mbank_deposits(data_root, 'p_m_23')
    return result


def evaluate_mbank_deposits(data_root, asset_id):
    p = data_root / asset_id
    df = read_m_transactions(p, asset_id)

    pattern = r"(NR 0\d{14})"
    df['lokata'] = df[MBANK_TITLE].str.extract(pattern, expand=False)   #.fillna('')

    result = df[df['lokata'].notnull()]
    # result.to_excel('deposits.xlsx')
    # piv = result.pivot(index='lokata', columns=MBANK_DESCRIPTION, values=MBANK_AMOUNT)
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
    deposits = evaluate_deposits(data_root, assets)
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
