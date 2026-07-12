# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"
from pathlib import Path
import pandas as pd


class NonCachedDataFrame:
    def __init__(self, **kwargs):
        self._data_frame = self.import_file(**kwargs)

    def __str__(self):
        raise NotImplementedError

    def df(self):
        assert self._data_frame is not None
        return self._data_frame

    def import_file(self, the_file: Path = None, **kwargs) -> pd.DataFrame:
        return self.import_data(the_file=the_file, **kwargs)

    def import_data(self, the_file: Path = None, **kwargs) -> pd.DataFrame:
        raise NotImplementedError
