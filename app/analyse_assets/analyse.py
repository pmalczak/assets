# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from analyse_assets.aquamarina import aquamarina, _garaz
from analyse_assets.horbaczewskiego import horbaczewskiego
from analyse_assets.kiemliczow_1 import kiemliczow_1
from analyse_assets.kiemliczow_3 import kiemliczow_3
from analyse_assets.opoczynska import opoczynska
from analyse_assets.rumiankowa import rumiankowa
from analyse_assets.starogajowa import starogajowa
from consolidate_and_drop_internal_transfers import consolidate_many_drop_internal_transfers
from data_root import get_online_data_root
from data_step.data_step import DATA_STEP
from importers.assets.data_model import AssetsFile, KindDomain
from importers.assets.read_assets import read_assets
from importers.mbank.read_m_transactions import read_m_transactions


def main():
    proj_root = Path(__file__).parent.parent
    DATA_STEP.init_steps(root=proj_root)

    assets = read_assets()
    assets = assets[assets[AssetsFile.KIND].str.startswith(KindDomain.MBANK)]
    assets = assets[assets[AssetsFile.CURRENCY] == 'PLN']
    assets = assets[AssetsFile.ID].tolist()

    data_root = get_online_data_root()
    result = []
    for asset in assets:
        df = read_m_transactions(data_root, asset)
        df["_source"] = asset

        result += [df]

    df, report, meta = consolidate_many_drop_internal_transfers(result)

    df['#Opis operacji'] = df['#Opis operacji'].replace({'PRZELEW WEWNĘTRZNY PRZYCHODZĄCY': ' WPŁYWY',
                                                         'PRZELEW ZEWNĘTRZNY PRZYCHODZĄCY': ' WPŁYWY',
                                                         'PRZELEW ZEWNĘTRZNY WYCHODZĄCY': ' WYDATKI',
                                                         'PRZELEW WEWNĘTRZNY WYCHODZĄCY': ' WYDATKI',
                                                         'PRZELEW SORBNET WYCHODZĄCY': ' WYDATKI',
                                                         })

    df['Data operacji'] = pd.to_datetime(df['#Data operacji'], format='%Y-%m-%d')

    df['ROK'] = df['Data operacji'].dt.year
    df['MIESIAC'] = df['Data operacji'].dt.month
    df['DZIEN'] = df['Data operacji'].dt.day

    p = Path(__file__).parent

    df = analyse_assets_proc(df, p)

    print(meta)

    fout = p / f'mbank_consolidated.xlsx'
    df.to_excel(fout, index=False)

    # fout = p / f'mbank_consolidated.parquet'
    # df.to_parquet(fout, compression=None)
    return


def analyse_assets_proc(df, p):
    result = {}

    fout = p / f'mbank_aquamarina.xlsx'
    df = aquamarina(df, fout, result)

    fout = p / f'mbank_horbaczewskiego.xlsx'
    df = horbaczewskiego(df, fout, result)

    fout = p / f'mbank_garaz.xlsx'
    df = _garaz(df, fout, result)

    fout = p / f'mbank_starogajowa.xlsx'
    df = starogajowa(df, fout, result)

    fout = p / f'mbank_kieliczow_1.xlsx'
    df = kiemliczow_1(df, fout, result)

    fout = p / f'mbank_kieliczow_3.xlsx'
    df = kiemliczow_3(df, fout, result)

    fout = p / f'mbank_kieliczow_4.xlsx'
    df = kiemliczow_3(df, fout, result)

    fout = p / f'mbank_rumiankowa.xlsx'
    df = rumiankowa(df, fout, result)

    fout = p / f'mbank_opoczynska.xlsx'
    df = opoczynska(df, fout, result)

    return df


if __name__ == '__main__':
    pd.options.mode.copy_on_write = True
    pd.options.future.infer_string = True

    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 5000)
    pd.set_option('display.colheader_justify', 'center')
    main()
