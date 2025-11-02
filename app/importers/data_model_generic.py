# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

import pandas as pd


class GenericStructureClass:
    def __init__(self):
        return

    def expected_columns(self) -> set:
        x = self.__class__.__name__
        s = f'"{x}.expected_columns()" not implemented'
        raise NotImplementedError(s)

    def check_structure(self, df: pd.DataFrame):
        cols = df.columns.tolist()
        cols = set(cols)
        diff = cols.symmetric_difference(self.expected_columns())
        if diff:
            raise ValueError(diff)


class DomainCheckerGeneric:
    def __init__(self, column):
        self.column = column

    def domain(self):
        raise NotImplementedError

    def is_in_domain(self, df: pd.DataFrame):
        x = df[self.column].unique().tolist()
        domain = self.domain()
        diff = set(x) - domain
        if diff:
            x = self.__class__.__name__
            s = f'{diff} values out of {self.column} domain in "{x}"'
            raise ValueError(s)
