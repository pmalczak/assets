# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from datetime import date

import pandas as pd

from importers.assets.data_model import AssetsDef
from fx.data_model import LastFx
from nbp_fx_repo.nbp_fx_rates_fetch import NBP_FX_DATE
from nbp_fx_repo.nbp_fx_repository import NBP_API_PLN, NBP_API_EUR


def get_last_fx(fx_rates: pd.DataFrame) -> pd.DataFrame:
    return _format_fx_rows(fx_rates[-1:])


def get_fx_as_of(fx_rates: pd.DataFrame, valuation_date: date) -> pd.DataFrame:
    cutoff = pd.Timestamp(valuation_date).normalize()
    index_dates = pd.to_datetime(fx_rates.index, errors="coerce")
    if not isinstance(index_dates, pd.DatetimeIndex):
        index_dates = pd.DatetimeIndex(index_dates)
    index_dates = index_dates.normalize()
    available = fx_rates.loc[index_dates <= cutoff]
    if available.empty:
        raise ValueError(f"Brak kursu FX na date lub wczesniej: {valuation_date}")
    return _format_fx_rows(available[-1:])


def _format_fx_rows(last_fx: pd.DataFrame) -> pd.DataFrame:
    last_fx = last_fx.copy()
    last_fx[AssetsDef.CURRENCY] = NBP_API_EUR
    last_fx = last_fx.reset_index()
    date_col = NBP_FX_DATE if NBP_FX_DATE in last_fx.columns else last_fx.columns[0]
    last_fx.rename(columns={NBP_API_EUR: LastFx.FX, date_col: AssetsDef.VALUE_DATE}, inplace=True)
    last_fx[AssetsDef.VALUE_DATE] = pd.to_datetime(last_fx[AssetsDef.VALUE_DATE]).dt.strftime("%Y-%m-%d")
    x = last_fx.copy()
    x[AssetsDef.CURRENCY] = NBP_API_PLN
    x["fx"] = 1.0
    result = pd.concat([last_fx, x])
    LastFx.check_structure(result)
    return result
