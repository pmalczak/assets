# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path
import pandas as pd

from importers.assets.data_model import AssetsFile, AssetsDef
from importers.assets.read_assets import read_assets
from check_wrong_catalogs import check_wrong_catalogs
from data_root import get_online_data_root
from data_step.data_step import DATA_STEP
from evaluators.evaluate_assets import evaluate_assets
from fx.data_model import LastFx
from nbp_fx_repo.nbp_fx_repository import NbpFxRepository, NBP_API_EUR


s = '________________________________________________\n'
col_space=15


def calculate_assets() -> pd.DataFrame:
    local_data_steps_root = Path(__file__).parent.parent
    DATA_STEP.init_steps(root=local_data_steps_root)

    # DATA_STEP.force_read_data()

    data_root = get_online_data_root()

    metadata_root: Path = DATA_STEP.metadata.get_metadata_root() / 'fx'
    if not metadata_root.is_dir():
        metadata_root.mkdir()

    fx_repo = NbpFxRepository(target_directory=metadata_root, min_year=2005)
    fx_rates = fx_repo.update_to_date()
    fx_rates = fx_rates[[NBP_API_EUR]]

    assets = read_assets()
    check_wrong_catalogs(data_root, assets)
    assets = evaluate_assets(data_root, assets, fx_rates)

    assets = assets.sort_values(by=[AssetsFile.GROUP, AssetsFile.ID])
    assets = assets[assets[AssetsDef.VALUE] != 0]
    assets = assets.drop(columns=[AssetsDef.NOTES, LastFx.FX])
    return assets


def main():
    # DATA_STEP.force_read_data()
    assets = calculate_assets()
    print(assets)
    print(s)
    assets.to_excel('assets_evaluation.xlsx', index=False)

    rap3(assets)
    rap2(assets)
    rap1_prn(assets)
    return


def rap3(assets):
    msg = 'RAP 3___________________________________________'
    print(msg)
    a1 = assets[[AssetsDef.TYPE,
                 AssetsDef.CURRENCY,
                 AssetsDef.EVALUATION_DATE, AssetsDef.VALUE]]
    g1 = a1.groupby([
        AssetsDef.EVALUATION_DATE,
        AssetsDef.TYPE,
    ]).agg({
        AssetsDef.VALUE: 'sum',
        AssetsDef.CURRENCY: 'first',  # waluta taka jak w grupie
    })

    g1[AssetsDef.VALUE] = (
        g1[AssetsDef.VALUE]
        .round()
        .astype(int)
        .map('{:,}'.format)
        .str.replace(',', ' ')
    )

    g1[AssetsDef.VALUE] = g1[AssetsDef.VALUE] + ' ' + g1[AssetsDef.CURRENCY]
    g1 = g1.drop(columns=[AssetsDef.CURRENCY])
    print(g1.to_string(col_space=col_space))

    # print(g1)
    print(s)


def rap2(assets):
    msg = 'RAP 2___________________________________________'
    print(msg)
    a1 = assets[[AssetsDef.TYPE,
                 # AssetsDef.EVALUATION_DATE,
                 AssetsDef.VALUE,
                 AssetsDef.VALUE_PLN,
                 AssetsDef.CURRENCY]]
    a1_g = a1.copy()
    a1_g[AssetsDef.TYPE] = 'Z RAZEM'
    a1 = pd.concat([a1, a1_g])
    g1 = a1.groupby([AssetsDef.CURRENCY, AssetsDef.TYPE]).sum().round().astype('int')
    g1[AssetsDef.VALUE] = g1[AssetsDef.VALUE].map('{:,}'.format).apply(lambda x: x.replace(',', ' '))
    g1[AssetsDef.VALUE] = g1[AssetsDef.VALUE] + ' ' + g1.index.get_level_values(AssetsDef.CURRENCY)

    g1[AssetsDef.VALUE_PLN] = g1[AssetsDef.VALUE_PLN].map('{:,}'.format).apply(lambda x: x.replace(',', ' '))
    print(g1.to_string(col_space=col_space))
    print(s)


def rap1_prn(assets):
    msg = 'RAP 1'
    print(msg)
    g1 = rap1(assets)
    print(g1.to_string(col_space=col_space))
    # print(s)


def rap1(assets: pd.DataFrame) -> pd.DataFrame:
    a1 = assets[[AssetsDef.GROUP, AssetsDef.CURRENCY, AssetsDef.VALUE_PLN]]
    a2 = a1.copy()
    a2[AssetsDef.GROUP] = 'Z RAZEM'
    a3 = a1.copy()
    a3[AssetsDef.CURRENCY] = 'RAZEM'
    a4 = a3.copy()
    a4[AssetsDef.GROUP] = 'Z RAZEM'

    # łączymy dane
    df = pd.concat([a1, a2, a3, a4])

    # grupowanie: GROUP + CURRENCY --> suma
    g1 = df.groupby([AssetsDef.GROUP, AssetsDef.CURRENCY]).sum()

    # pivot: waluty w kolumnach
    g1 = g1.unstack(AssetsDef.CURRENCY).fillna(0)

    # usuwamy MultiIndex kolumn po pivotowaniu
    g1.columns = g1.columns.get_level_values(1)

    # formatowanie kwot
    for col in g1.columns:
        g1[col] = (
            g1[col]
            .round()
            .astype(int)
            .map('{:,}'.format)
            .str.replace(',', ' ')
        )

    return g1


def rap1_0(assets):
    a1 = assets[[AssetsDef.GROUP, AssetsDef.VALUE_PLN]]
    a2 = a1.copy()
    a2[AssetsDef.GROUP] = 'Z RAZEM'

    df = pd.concat([a1, a2])
    g1 = df.groupby([AssetsDef.GROUP]).sum().round().astype('int')
    g1[AssetsDef.VALUE_PLN] = g1[AssetsDef.VALUE_PLN].map('{:,}'.format).apply(lambda x: x.replace(',', ' '))
    return g1



if __name__ == '__main__':
    pd.options.mode.copy_on_write = True
    pd.options.future.infer_string = True

    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 5000)
    pd.set_option('display.colheader_justify', 'center')

    main()
