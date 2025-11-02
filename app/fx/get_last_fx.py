# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

import pandas as pd

from importers.assets.data_model import AssetsDef
from fx.data_model import LastFx
from nbp_fx_repo.nbp_fx_rates_fetch import NBP_FX_DATE
from nbp_fx_repo.nbp_fx_repository import NBP_API_PLN, NBP_API_EUR


def get_last_fx(fx_rates: pd.DataFrame) -> pd.DataFrame:
    last_fx = fx_rates[-1:]
    last_fx[AssetsDef.CURRENCY] = NBP_API_EUR
    last_fx.reset_index(inplace=True)
    last_fx.rename(columns={NBP_API_EUR: LastFx.FX,
                            NBP_FX_DATE: AssetsDef.VALUE_DATE}, inplace=True)
    x = last_fx.copy()
    x[AssetsDef.CURRENCY] = NBP_API_PLN
    x['fx'] = 1.0
    last_fx = pd.concat([last_fx, x])
    LastFx.check_structure(last_fx)
    return last_fx
