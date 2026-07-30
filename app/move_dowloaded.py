# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from app_proc.data_root import get_cash_pool_root, get_online_data_root
from maintenance.move_downloaded_results import MoveResult
from maintenance.move_mbank_files import move_mbank_files
from maintenance.move_revolut_files import move_revolut_files

pd.options.future.infer_string = True


def run_move_downloaded(
    assets_root: Path | None = None,
    cash_pool_root: Path | None = None,
) -> list[MoveResult]:
    assets_root = assets_root or get_online_data_root()
    cash_pool_root = cash_pool_root or get_cash_pool_root()
    cash_pool_root.mkdir(parents=True, exist_ok=True)

    download = Path().home() / 'Downloads'
    assert download.is_dir()

    results: list[MoveResult] = []
    results.extend(move_revolut_files(cash_pool_root, 'p_re', assets_root=assets_root))
    results.extend(move_revolut_files(cash_pool_root, 'g_re', assets_root=assets_root))
    results.extend(move_mbank_files(cash_pool_root, download))
    # Luźne CSV mBank czasem lądują w assets/ — destynacja i tak to cash_pool.
    results.extend(move_mbank_files(cash_pool_root, assets_root))
    return results


if __name__ == '__main__':
    for result in run_move_downloaded():
        destination = result.destination if result.destination is not None else '—'
        print(f'{result.action}: {result.source} -> {destination} ({result.kind})')
