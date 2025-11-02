# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from data_root import get_online_data_root

pd.options.mode.copy_on_write = True
pd.options.future.infer_string = True


def get_downloaded() -> list:
    dowload = Path().home() / 'Downloads'
    assert dowload.is_dir()

    lst = dowload.glob('*_*_*.csv')
    lst = filter(lambda x: len(x.stem) == 22, lst)
    lst = list(lst)
    return lst


def main():
    data_root = get_online_data_root()
    target_dirs = get_target_dirs(data_root)
    lst = get_downloaded()
    print(len(lst))

    for f in lst:
        move_file(f, data_root, target_dirs)
    return


def get_target_dirs(data_root: Path) -> dict:
    result = data_root.glob('*')
    result = filter(lambda x: x.is_dir(), result)
    result = map(lambda x: x.name, result)
    result = map(lambda x: x.split('_'), result)
    result = filter(lambda x: len(x) >= 4, result)
    result = map(lambda x: ('_'.join(x), x[3]), result)
    result = list(result)
    result = {v:k for k, v in result}
    return result


def move_file(f: Path, data_root, target_dirs: dict):
    segments = f.stem.split('_')
    if len(segments) != 3:
        raise ValueError(f)

    key = f.stem.split('_')[0]
    assert len(key) == 8
    key = key[4:]
    target_dir = data_root / target_dirs[key]
    dst = target_dir / f.name
    print(f'moving {f} to {dst}')
    f.replace(dst)
    return


if __name__ == '__main__':
    main()
