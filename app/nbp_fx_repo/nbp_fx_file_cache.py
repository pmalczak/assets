# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

import datetime
from pathlib import Path

import pandas as pd

from cache.cached_data_frame import CachedDataFrame, DataFrameCacheInvalid
from nbp_pl_api.nbp_fx_rates_fetch import NBP_FX_DATE, nbp_fx_rates_fetch


class NbpFxFileCache(CachedDataFrame):
    """Cache kursów NBP A.

    Lata zamknięte: ``NBP_FX_RATES.{year}.parquet`` (bez refetch).
    Rok bieżący: ``NBP_FX_RATES.{year}.{mm_dd}_{HH}.parquet`` — bucket godzinowy,
    żeby przed publikacją tabeli A na dziś nie „zabetonować” porannego fetchu
    do północy, a jednocześnie nie spamować API (max ~1×/h).
    """

    def __init__(self, target_directory: Path, year: int, delete_outdated_cache_files):
        self.target_directory = target_directory
        self.year = year
        super().__init__(output_directory=target_directory, delete_outdated_cache_files=delete_outdated_cache_files)

    def import_data(self, **kwargs) -> pd.DataFrame:
        _result = nbp_fx_rates_fetch(self.year)
        _result.drop(columns=['currency'], inplace=True)

        result = pd.pivot(_result, values=['mid'], index=[NBP_FX_DATE], columns=['code'])
        columns = list(map(lambda x: x[1], result.columns))
        result.columns = columns

        result.reset_index(inplace=True)
        result.set_index(NBP_FX_DATE, inplace=True)
        return result

    def parquet_file_name(self, the_file: Path = None, **_) -> Path:
        today = datetime.datetime.now()
        if today.year > self.year:
            name = f"NBP_FX_RATES.{self.year}.parquet"
        else:
            # Kalendarzowy dzień + godzina: refetch co najwyżej raz na godzinę.
            stamp = today.strftime("%m_%d_%H")
            name = f"NBP_FX_RATES.{self.year}.{stamp}.parquet"
        return self.target_directory / name

    def validate(self, input_file_digest: Path, parquet_file: Path, **kwargs):
        if not parquet_file.is_file():
            raise DataFrameCacheInvalid

    def md5_file_name(self, the_file: Path = None, **_) -> Path:
        raise NotImplementedError

    def delete_outdated_files(self, **kwargs):
        parquet = self.parquet_file_name(**kwargs)
        core, ext = parquet.stem, parquet.suffix

        x = core.split('.')
        if len(x) == 2:
            return
        elif len(x) >= 3:
            # NBP_FX_RATES.{year}.* — usuń inne buckety (dzień/godzina) tego roku.
            parquet_template = f"{x[0]}.{x[1]}.*{ext}"
            lst = list(parquet.parent.glob(parquet_template))
            lst = list(filter(lambda path: path != parquet, lst))
            list(map(lambda path: path.unlink(), lst))
            return
        else:
            raise ValueError
