# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"


class Dependencies:
    def __init__(self):
        self._value = {'top': []}

    def update(self, item, value):
        _deps = self._value[item]
        if value not in _deps:
            _deps += [value]
        return

    def get(self, item):
        result = self._value[item]
        return result

    def create(self, item):
        try:
            _ = self._value[item]
        except KeyError:
            self._value[item] = []
        return
