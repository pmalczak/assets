# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

import pandas as pd


class DataStepFrame:
    def __init__(self, status=None, data=None, dependencies=None, data_set=None):
        assert isinstance(status, str)
        assert isinstance(data, pd.DataFrame) or data is None
        assert isinstance(dependencies, list) or dependencies is None
        assert isinstance(data_set, str) or data_set is None

        self._status = status
        self._data = data
        self._dependencies = dependencies if dependencies else []
        self._data_set = data_set

        self._column_name = None

    def __str__(self):
        t = self._data.__class__.__name__
        if t == 'DataFrame':
            stat = f'  {self._status} in "{self._data_set}"' if self._data_set else ''
            result = f'{t}/{str(self._data.shape)}{stat}'
        elif t == 'Series':
            col = self._column_name + '/'
            result = f'{col}{t}/{len(self._data)}'
        else:
            raise ValueError
        return result

    def get_status(self) -> str:
        return self._status

    def set_data(self, data) -> None:
        self._data = data

    def data_frame(self) -> pd.DataFrame:
        assert isinstance(self._data, pd.DataFrame)
        return self._data

    def set_dependencies(self, deps) -> None:
        if isinstance(deps, str):
            self._dependencies += [deps]
        elif isinstance(deps, list):
            self._dependencies += deps
        else:
            raise ValueError

    def set_column_name(self, name: str) -> None:
        self._column_name = name

    def get_column_name(self) -> str:
        return self._column_name

    def get_data_file_name(self) -> str:
        if self._data_set is None:
            raise ValueError
        return self._data_set
