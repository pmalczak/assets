# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"
import pandas as pd

from importers.assets.data_model import AssetsDef, Properties, OperationDomain
from importers.assets.read_assets import get_assets_file


def evaluate_assets_file(rodzaj_importu, assets_file_row):
    f = get_assets_file()

    if rodzaj_importu.startswith('assets.IKE-'):
        df = _read_content(f, assets_file_row)
        df['Data'] = df['Data'].dt.strftime('%Y-%m-%d')
        last = df[-1:]
        for i, row in last.iterrows():
            assets_row = AssetsDef.as_assets_row(assets_file_row)
            assets_row[AssetsDef.EVALUATION_DATE] = row['Data']
            assets_row[AssetsDef.VALUE] = row['wartość']
            break
        data = [assets_row]

        result = pd.DataFrame(data=data)
        AssetsDef.check_structure(result)
        return result

    if rodzaj_importu == 'assets.properties':
        df = _read_content(f, assets_file_row)
        Properties.check_structure(df, file=f)
        df = df[df[Properties.OPERATION] != OperationDomain.SOLD]
        # leave only one record - the latest one - for each propertie
        df_sorted = df.sort_values([Properties.ID, Properties.DATE], ascending=[True, False])
        df = df_sorted.drop_duplicates(subset=Properties.ID, keep="first")

        result = []
        for i, row in df.iterrows():
            assets_row = AssetsDef.as_assets_row(assets_file_row)
            assets_row[AssetsDef.ID] = row[AssetsDef.ID]
            assets_row[AssetsDef.EVALUATION_DATE] = row[Properties.DATE]
            assets_row[AssetsDef.VALUE] = row[Properties.VALUE]
            result += [assets_row]

        result = pd.DataFrame(data=result)
        AssetsDef.check_structure(result)
        return result

    elif rodzaj_importu == 'assets.rocky-iv':
        # df = read_regnolgy_transactions(p)
        df = _read_content(f, assets_file_row)
        last = df[-1:]
        for i, row in last.iterrows():
            assets_row1 = AssetsDef.as_assets_row(assets_file_row)
            assets_row1[AssetsDef.VALUE] = row['wartość']
            assets_row1[AssetsDef.EVALUATION_DATE] = row['Data']
            break
        data = [assets_row1]
        result = pd.DataFrame(data=data)
        AssetsDef.check_structure(result)
        return result

    elif rodzaj_importu == 'assets.cash':
        df = _read_content(f, assets_file_row)
        df_sorted = df.sort_values(['waluta', 'Data'], ascending=[True, False])
        df = df_sorted.drop_duplicates(subset='waluta', keep="first")

        result = []
        for i, row in df.iterrows():
            assets_row = AssetsDef.as_assets_row(assets_file_row)
            assets_row[AssetsDef.ID] = row['waluta']
            assets_row[AssetsDef.EVALUATION_DATE] = row['Data']
            assets_row[AssetsDef.VALUE] = row['wartość']
            result += [assets_row]

        result = pd.DataFrame(data=result)
        AssetsDef.check_structure(result)
        return result

    elif rodzaj_importu == 'assets.rocky-iv':
        print(f'brakujący typ: {rodzaj_importu}')
        return None

    else:
        raise ValueError(f'brakujący typ: {rodzaj_importu}')


def _read_content(f, assets_file_row: pd.Series = None):
    kind: str = assets_file_row[AssetsDef.KIND]
    sheet = kind.split('.')[1]

    df = pd.read_excel(f, sheet_name=sheet)
    return df
