# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path
import pandas as pd

from importers.assets.data_model import AssetsFile, KindDomain
from importers.assets.read_assets import read_assets
from consolidate_and_drop_internal_transfers import consolidate_many_drop_internal_transfers
from data_root import get_online_data_root
from data_step.data_step import DATA_STEP
from importers.mbank.read_m_transactions import read_m_transactions

pd.options.mode.copy_on_write = True
pd.options.future.infer_string = True


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

    cleaned, report, meta = consolidate_many_drop_internal_transfers(result)
    print(meta)

    # df = pd.concat([df1, df2])
    p = Path(__file__).parent
    fout = p / f'mbank_consolidated.xlsx'
    cleaned.to_excel(fout, index=False)

    fout = p / f'mbank_consolidated.parquet'
    cleaned.to_parquet(fout, compression=None)
    return


if __name__ == '__main__':
    main()
