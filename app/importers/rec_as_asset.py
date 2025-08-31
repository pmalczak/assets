# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"


def rec_as_asset(asset_id: str, date: str, value: float | int, iban: str):
    d = {
        'id': asset_id,
        'data wyceny': date,
        'wartość': value,
        'IBAN': iban
    }
    return d
