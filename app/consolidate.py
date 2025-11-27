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

    df, report, meta = consolidate_many_drop_internal_transfers(result)

    df['Data operacji'] = pd.to_datetime(df['#Data operacji'], format='%Y-%m-%d')

    df['ROK'] = df['Data operacji'].dt.year
    df['MIESIAC'] = df['Data operacji'].dt.month
    df['DZIEN'] = df['Data operacji'].dt.day

    p = Path(__file__).parent
    #
    mask = (
            df["#Nadawca/Odbiorca"].str.contains("AQUAMARINA") |
            df["#Nadawca/Odbiorca"].str.contains("MIĘDZYZDROJE") |
            df["#Nadawca/Odbiorca"].str.contains("MARINA INVEST") #
    )
    mask2 = df["#Numer konta"].str.contains("10124069600163204573190024")

    df_aquamarina = df[mask | mask2].copy()
    fout = p / f'mbank_aquamarina.xlsx'
    df_aquamarina.to_excel(fout, index=False)
    df_aquamarina = df_aquamarina[['ROK', '#Kwota', '#Opis operacji']]
    total = df_aquamarina.copy()
    total['#Opis operacji'] = 'TOTAL'
    piv = pd.concat([df_aquamarina, total])
    tabela = piv.pivot_table(
        index='ROK',
        columns='#Opis operacji',
        values='#Kwota',
        aggfunc='sum',
        fill_value=0
    )
    tabela = tabela.round().astype('int').map('{:,}'.format).replace(',', ' ')

    print(tabela.to_string(col_space=15))

    df = df[~(mask | mask2)].copy()

    print(meta)

    # df = pd.concat([df1, df2])
    fout = p / f'mbank_consolidated.xlsx'
    df.to_excel(fout, index=False)

    fout = p / f'mbank_consolidated.parquet'
    df.to_parquet(fout, compression=None)
    return


if __name__ == '__main__':
    pd.options.mode.copy_on_write = True
    pd.options.future.infer_string = True

    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 5000)
    pd.set_option('display.colheader_justify', 'center')
    main()
