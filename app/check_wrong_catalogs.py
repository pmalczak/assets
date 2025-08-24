# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd


def check_wrong_catalogs(data_root: Path, assets: pd.DataFrame):
    dir = data_root.glob('*')
    dir = filter(lambda x: x.is_dir(), dir)
    dir = map(lambda x: x.name, dir)
    dir = list(dir)
    dir = pd.DataFrame(data={
        'id': dir,
        # 'x': 1,
    })
    _assets = assets.copy()
    _assets['x'] = 1
    result = dir.merge(_assets, on='id', how='left')
    result = result[result['x'].isnull()]
    result = result[['id']].rename(columns={'id': 'nadmiarowe katalogi nieujawnione w "assets.xlsx"'})
    if not result.empty:
        print(result)
    return
