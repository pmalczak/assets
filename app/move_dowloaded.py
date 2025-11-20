# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from data_root import get_online_data_root
from maintenance.move_mbank_files import move_mbank_files

pd.options.mode.copy_on_write = True
pd.options.future.infer_string = True


def move_revolut_files():
    return


if __name__ == '__main__':
    data_root = get_online_data_root()
    download = Path().home() / 'Downloads'
    assert download.is_dir()

    move_revolut_files()
    move_mbank_files(data_root, download)
    move_mbank_files(data_root, data_root)

