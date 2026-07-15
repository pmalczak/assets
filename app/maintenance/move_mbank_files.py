# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

from maintenance.move_downloaded_results import ACTION_MOVED, KIND_MBANK, MoveResult


def get_downloaded(download) -> list:
    lst = download.glob('*_*_*.csv')
    lst = filter(lambda x: len(x.stem) == 22, lst)
    lst = list(lst)
    return lst


def move_mbank_files(data_root, download) -> list[MoveResult]:
    target_dirs = get_target_dirs(data_root)
    lst = get_downloaded(download)

    results: list[MoveResult] = []
    for f in lst:
        results.append(move_file(f, data_root, target_dirs))
    return results


def get_target_dirs(data_root: Path) -> dict:
    result = data_root.glob('*')
    result = filter(lambda x: x.is_dir(), result)
    result = map(lambda x: x.name, result)
    result = map(lambda x: x.split('_'), result)
    result = filter(lambda x: len(x) >= 4, result)
    result = map(lambda x: ('_'.join(x), x[3]), result)
    result = list(result)
    result = {v: k for k, v in result}
    return result


def move_file(f: Path, data_root, target_dirs: dict) -> MoveResult:
    segments = f.stem.split('_')
    if len(segments) != 3:
        raise ValueError(f)

    key = f.stem.split('_')[0]
    assert len(key) == 8
    key = key[4:]
    target_dir = data_root / target_dirs[key]
    dst = target_dir / f.name
    f.replace(dst)
    return MoveResult(source=f, destination=dst, action=ACTION_MOVED, kind=KIND_MBANK)
