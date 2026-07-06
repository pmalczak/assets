# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from main_proc.data_root import get_online_data_root
from maintenance.move_mbank_files import move_mbank_files
from maintenance.move_revolut_files import move_revolut_files

pd.options.future.infer_string = True

if __name__ == '__main__':
    data_root = get_online_data_root()
    download = Path().home() / 'Downloads'
    assert download.is_dir()

    move_revolut_files(data_root, 'p_re')
    move_revolut_files(data_root, 'g_re')
    move_mbank_files(data_root, download)
    move_mbank_files(data_root, data_root)
