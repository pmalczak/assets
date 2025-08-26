# -*- coding: utf-8 -*-
__author__ = 'pmalczak@gmail.com'

import pandas as pd
from pathlib import Path
from io import StringIO
import platform


def read_revolut_csv_file(input_file: Path) -> pd.DataFrame:
    sys = platform.system()
    if sys == 'Linux':
        arg = {}
    elif sys == 'Windows':
        arg = {'encoding': 'utf-8'}
    else:
        raise ValueError(sys)
    with open(input_file, 'r', **arg) as f:
        in_content = f.read()
        str_io = StringIO(in_content)
        result = pd.read_csv(str_io)

    return result
