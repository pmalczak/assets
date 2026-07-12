# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"
import datetime
import io
import json

import pandas as pd
import requests

NBP_API_DATE_FORMAT = '%Y-%m-%d'
NBP_FX_DATE = 'DATE'


def nbp_fx_rates_fetch(year: int) -> pd.DataFrame:
    q = (
        (f'{year}-01-01', f'{year}-03-31'),
        (f'{year}-04-01', f'{year}-06-30'),
        (f'{year}-07-01', f'{year}-09-30'),
        (f'{year}-10-01', f'{year}-12-31'),
    )
    today = datetime.datetime.today().strftime(NBP_API_DATE_FORMAT)

    result = []
    for start, _end in q:
        if start < today:
            end = today if today < _end else _end
            r = _fetch_nbp_fx_rates(start, end)
            result += [r]
    result = pd.concat(result)
    return result


def _fetch_nbp_fx_rates(start: str, end: str) -> pd.DataFrame:
    url = f'http://api.nbp.pl/api/exchangerates/tables/A/{start}/{end}/?format=json'
    resource = requests.get(url)
    if resource.status_code != 200:
        s = f'{url} / {resource.content}'
        raise ReferenceError(s)

    csvio = io.BytesIO(resource.content)
    x = json.load(csvio)

    result = []
    for row in x:
        r = pd.DataFrame(row['rates'])
        r[NBP_FX_DATE] = row['effectiveDate']
        result += [r]

    result = pd.concat(result)
    return result


def nbp_fx_is_available(date: str):
    try:
        x = _fetch_nbp_fx_rates(date, date)
        return True
    except ReferenceError as e:
        return False
