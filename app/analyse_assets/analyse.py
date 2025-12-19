# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"
from pathlib import Path
import pandas as pd

from analyse_assets.aquamarina import aquamarina
from analyse_assets.garaz import garaz
from analyse_assets.data_model import AssetRw
from analyse_assets.horbaczewskiego import horbaczewskiego
from analyse_assets.kiemliczow_1 import kiemliczow_1
from analyse_assets.kiemliczow_3 import kiemliczow_3
from analyse_assets.kiemliczow_4 import kiemliczow_4
from analyse_assets.opoczynska import opoczynska
from analyse_assets.rumiankowa import rumiankowa
from analyse_assets.select_asset import print_asset
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
    # DATA_STEP.force_read_data()
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
    df = AssetRw.extract_ymd(df)

    p = Path(__file__).parent
    df = analyse_assets_proc(df, p)
    print(meta)

    file_out = p / f'mbank_consolidated.xlsx'
    df.to_excel(file_out, index=False)

    # file_out = p / f'mbank_consolidated.parquet'
    # df.to_parquet(file_out, compression=None)
    return


def analyse_assets_proc(df, p):
    result = {}

    x = {
        'mbank_aquamarina.xlsx': aquamarina,
        'mbank_horbaczewskiego.xlsx':horbaczewskiego,
        'mbank_garaz.xlsx': garaz,
        'mbank_starogajowa.xlsx': starogajowa,
        'mbank_kiemliczow_1.xlsx': kiemliczow_1,
        'mbank_kiemliczow_4.xlsx': kiemliczow_4,
        'mbank_kiemliczow_3.xlsx': kiemliczow_3,
        'mbank_rumiankowa.xlsx': rumiankowa,
        'mbank_opoczynska.xlsx': opoczynska,
    }
    for file_name, proc in x.items():
        file_out = p / file_name
        df, r = proc(df)
        # AssetRw.check_values(r)
        result[file_out] = r
        print_asset(r, file_out, result)

    for file, _df in result.items():
        _df.to_excel(file, index=False)

    return df


if __name__ == '__main__':
    pd.options.mode.copy_on_write = True
    pd.options.future.infer_string = True

    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 5000)
    pd.set_option('display.colheader_justify', 'center')
    main()
