# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

import hashlib
import pickle
from pathlib import Path
import pandas as pd
from pyarrow import ArrowInvalid

from cache.non_cached_data_frame import NonCachedDataFrame
from data_step.parquet_safe import write_dataframe_parquet
from utils.create_missing_path import create_missing_paths


class DataFrameCacheInvalid(Exception):
    pass


class CachedDataFrame(NonCachedDataFrame):
    def __init__(self, delete_outdated_cache_files: bool = True, **kwargs):
        self._parquet_file_name: Path = None
        self._xlsx_file_name = None
        self._md5_file_name = None
        super().__init__(**kwargs)
        if delete_outdated_cache_files:
            try:
                self.delete_outdated_files(**kwargs)
            except NotImplementedError:
                pass

    def __str__(self):
        return self.parquet_file_name()

    @staticmethod
    def create_file_core_name(the_file: Path, extension: str) -> Path:
        if the_file is None:
            raise ValueError
        name = the_file.name.split('.')
        assert len(name) >= 2
        name = '.'.join(name[0:-1])
        return the_file.parent / f'{name}.{extension}'

    def parquet_file_name(self, the_file: Path = None, **_) -> Path:
        return self.create_file_core_name(the_file, 'parquet')

    def xlsx_file_name(self, **kwargs) -> Path:
        raise NotImplementedError

    def md5_file_name(self, the_file: Path = None, **_) -> Path:
        return self.create_file_core_name(the_file, 'md5')

    def validate(self, input_file_digest: Path, parquet_file: Path, **kwargs):
        md5_file = self.md5_file_name(the_file=input_file_digest)
        if not md5_file.is_file():
            raise DataFrameCacheInvalid
        if not parquet_file.is_file():
            raise DataFrameCacheInvalid

        with open(md5_file, "rb") as f:
            value = pickle.load(f)
        assert isinstance(value, dict)
        if 'input_file_digest' not in value:
            raise DataFrameCacheInvalid
        if 'parquet_digest' not in value:
            raise DataFrameCacheInvalid

        digest = self._calc_md5(input_file_digest)
        if value['input_file_digest'] != digest:
            raise DataFrameCacheInvalid

        digest = self._calc_md5(parquet_file)
        if value['parquet_digest'] != digest:
            raise DataFrameCacheInvalid

    def _import_and_save_data(self, the_file, **kwargs) -> pd.DataFrame:
        result = self.import_data(the_file=the_file, **kwargs)
        create_missing_paths(self._parquet_file_name.parent)

        while True:
            try:
                write_dataframe_parquet(result, self._parquet_file_name, compression="gzip")
                break
            except ArrowInvalid as e:
                column = e.args[1]
                assert column.startswith('Conversion failed for column')
                column = column.split(' ')
                column = column[4]
                result.drop(columns=column, inplace=True)
                continue

        if self._xlsx_file_name:
            result.to_excel(self._xlsx_file_name, index=False)
        if self._md5_file_name:
            self.save_md5(the_file, self._parquet_file_name, self._md5_file_name)
        return result

    def import_file(self, the_file: Path = None, **kwargs) -> pd.DataFrame:
        self._parquet_file_name = self.parquet_file_name(the_file=the_file, **kwargs)
        try:
            self._xlsx_file_name = self.xlsx_file_name()
        except NotImplementedError:
            pass
        try:
            self._md5_file_name = self.md5_file_name(the_file=the_file, **kwargs)
        except NotImplementedError:
            pass

        try:
            self.validate(the_file, self._parquet_file_name, **kwargs)
            result = pd.read_parquet(self._parquet_file_name)

        except DataFrameCacheInvalid:
            result = self._import_and_save_data(the_file, **kwargs)
            try:
                self.delete_outdated_files()
            except NotImplementedError:
                pass

        if self._xlsx_file_name:
            assert self._xlsx_file_name.is_file()
        if self._md5_file_name:
            assert self._md5_file_name.is_file()

        return result

    def delete_outdated_files(self, **kwargs):
        raise NotImplementedError

    # def import_non_cached_file(self, the_file: Path = None, **kwargs) -> pd.DataFrame:
    #     return super(CachedDataFrame, self).import_non_cached_file(the_file=the_file, **kwargs)

    def save_md5(self, gnucash_file: Path, parquet_file, md5_file):
        gnucash_digest = self._calc_md5(gnucash_file)
        parquet_digest = self._calc_md5(parquet_file)

        value = {'input_file_digest': gnucash_digest,
                 'parquet_digest': parquet_digest}
        with open(md5_file, "wb") as f:
            pickle.dump(value, f)

    @staticmethod
    def _calc_md5(a_file: Path):
        md5hash = hashlib.md5()
        with open(a_file, 'rb') as f:
            content = f.read()
            md5hash.update(content)
        digest = md5hash.hexdigest()
        return digest
