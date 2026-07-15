# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from app_proc.data_root import get_online_data_root
from maintenance.move_downloaded_results import MoveResult
from maintenance.move_mbank_files import move_mbank_files
from maintenance.move_revolut_files import move_revolut_files

pd.options.future.infer_string = True


def run_move_downloaded(data_root: Path | None = None) -> list[MoveResult]:
    data_root = data_root or get_online_data_root()
    download = Path().home() / 'Downloads'
    assert download.is_dir()

    results: list[MoveResult] = []
    results.extend(move_revolut_files(data_root, 'p_re'))
    results.extend(move_revolut_files(data_root, 'g_re'))
    results.extend(move_mbank_files(data_root, download))
    results.extend(move_mbank_files(data_root, data_root))
    return results


if __name__ == '__main__':
    for result in run_move_downloaded():
        destination = result.destination if result.destination is not None else '—'
        print(f'{result.action}: {result.source} -> {destination} ({result.kind})')
