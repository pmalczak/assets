# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"
import pandas as pd

from importers.assets.data_model import AssetsDef
from importers.assets.read_assets import get_assets_file


def evaluate_assets_file_content(assets_file_row: pd.Series = None):
    f = get_assets_file()
    kind: str = assets_file_row[AssetsDef.KIND]
    sheet = kind.split('.')[1]

    df = pd.read_excel(f, sheet_name=sheet)
    df['Data'] = df['Data'].dt.strftime('%Y-%m-%d')
    last =df[-1:]
    for i, row in last.iterrows():
        assets_row1 = AssetsDef.as_assets_row(assets_file_row)
        assets_row1[AssetsDef.EVALUATION_DATE] = row['Data']
        assets_row1[AssetsDef.VALUE] = row['wartość']
        break
    data = [assets_row1]

    result = pd.DataFrame(data=data)
    AssetsDef.check_structure(result)
    return result
