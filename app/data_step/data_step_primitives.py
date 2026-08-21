# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"
import os
from pathlib import Path

import pandas as pd

from data_step.data_step_frame import DataStepFrame
from data_step.data_strep_data_types import REFRESHED, CACHED
from data_step.metadata_class import Metadata, MetadataUpdateError, MTIME, DIGEST
from data_step.metadata_primitives_class import HOME_PATH
from data_step.parquet_safe import write_dataframe_parquet


class DataStepPrimitives:
    def __init__(self, data_steps: str, meta_parameters: str = ''):
        assert isinstance(meta_parameters, str)
        self.data_steps = data_steps
        self.metadata = None
        self._dependencies_stack = None
        self._dependencies = None
        self._cache = None

        # self._meta_parameters = meta_parameters
        self.printing_shift = 0

        self._initialised = False
        self._data_steps_root: Path | None = None

    def find_data_step_root(self, start: Path, markers: str = "data_steps") -> Path:
        """
        Finds the project root by walking up the directory tree
        until one of the marker files/directories is found.
        """
        current = Path(start).resolve().parent
        for directory in (current, *current.parents):
            d = directory / markers
            if d.exists():
                return d

        raise RuntimeError(f"{markers} Project root not found in {start}")

    def is_initialised(self):
        if not self._initialised:
            s = (f'{self.__class__.__name__} not initialised\n'
                 f'include following code snippet\n'
                 f'local_data_steps_root = Path(__file__).parent.parent\n'
                 f'DATA_STEP.init_steps(root=local_data_steps_root)')
            raise ReferenceError(s)

    def _reset_dependency_stack(self) -> None:
        """Sentinel 'top' musi zawsze zostać — inaczej kolejny obtain → IndexError."""
        self._dependencies_stack = ["top"]

    def _ensure_dependency_stack(self) -> None:
        if not self._dependencies_stack:
            self._reset_dependency_stack()

    def _pop_dependency_frame(self, product: str) -> str:
        """Zdejmij ramkę obtain; nigdy nie zdejmuj sentinela 'top'."""
        self._ensure_dependency_stack()
        if self._dependencies_stack[-1] == product:
            return self._dependencies_stack.pop()
        # Stos uszkodzony (np. reset mid-flight) — nie zdejmuj 'top'.
        if self._dependencies_stack[-1] == "top":
            return "top"
        return self._dependencies_stack.pop()

    def read_featured_file(self, data_file: Path) -> pd.DataFrame:
        self.is_initialised()
        assert isinstance(data_file, Path)

        _, extension = os.path.splitext(data_file.name)

        if extension == '.parquet':
            result = pd.read_parquet(data_file)
        elif extension == '.pickle':
            result = pd.read_pickle(data_file, compression=None)
        elif extension == '.xlsx':
            result = pd.read_excel(data_file, engine='openpyxl')
        else:
            raise NotImplementedError(extension)
        assert isinstance(result, pd.DataFrame)
        return result

    @staticmethod
    def _create_missing_directories(data_file: Path):
        p = data_file.parent
        stack = []
        while True:
            if p.is_dir():
                break
            stack += [p.name]
            p = p.parent
        stack.reverse()
        for name in stack:
            p = p / name
            p.mkdir()
        return

    def save_to_featured_file(self, data, data_file: Path) -> None:
        self.is_initialised()
        assert isinstance(data, pd.DataFrame)
        assert isinstance(data_file, Path)
        assert not str(data_file).startswith(HOME_PATH)
        self._create_missing_directories(data_file)

        _, extension = os.path.splitext(data_file.name)
        if extension == '.parquet':
            compression = None
            if '.gzip.parquet' in data_file.name:
                compression = 'gzip'
            try:
                write_dataframe_parquet(data, data_file, compression=compression)
            except Exception as e:
                data.info()
                raise
        elif extension == '.pickle':
            if '.gzip.' in data_file.name:
                raise ValueError
            data.to_pickle(str(data_file), compression=None)
        elif extension == '.xlsx':
            data.to_excel(data_file, index=False)
        else:
            raise NotImplementedError(extension)

    def get_absolute_file_path(self, resource: str) -> Path:
        self.is_initialised()
        assert isinstance(resource, str)
        result = self.metadata.token_as_path(resource)
        self._create_missing_directories(result)
        return result

    def _obtain_from_cache_or_collect(self,
                                      data_collector,
                                      product: str,
                                      source_item: (str, None),
                                      keep_cached: bool,
                                      **kwargs) -> DataStepFrame:
        self.is_initialised()
        try:
            self.printing_shift += 4
            self.metadata.is_updated(product)
            if source_item:
                self.metadata.is_updated(source_item)
            if product in self._cache:
                result = self._cache[product]
            else:
                result = self.__read_file(product, source_item)
                if keep_cached:
                    self._cache[product] = result
            return result
        except (MetadataUpdateError, KeyError, FileNotFoundError):
            self.metadata.updated_stat_cache.pop(product, None)
            if source_item:
                self.metadata.updated_stat_cache.pop(source_item, None)
            result = self.__collect(data_collector, source_item, product, keep_cached, **kwargs)
            return result

        finally:
            # self.metadata.force_read_data(False)
            self.printing_shift -= 4

    def _add_arguments_to_dependencies(self, output_file_name, **kwargs) -> None:
        for _, arg_value in kwargs.items():
            if isinstance(arg_value, DataStepFrame):
                v = arg_value.get_data_file_name()
                self._add_dependent(output_file_name, v)
        return

    def __collect(self, data_collector,
                  input_resource: str, product: str, keep_cached: bool, **kwargs) -> DataStepFrame:
        if input_resource is not None:
            _source_file_path = self.metadata.token_as_path(input_resource)

            kwargs['source_file'] = _source_file_path
        result = data_collector(**kwargs)

        if isinstance(result, DataStepFrame):
            result = result.data_frame()

        if not isinstance(result, pd.DataFrame):
            raise TypeError

        result = self.__save(REFRESHED, product, result)
        if keep_cached:
            self._cache[product] = result
        return result

    @staticmethod
    def _create_data_structure_descriptor(data) -> dict:
        columns = data.columns
        result = {}
        for column in columns:
            result[column] = data.dtypes[column].name
        return result

    def save(self, status, data_file_name, data) -> DataStepFrame:
        return self.__save(status, data_file_name, data)

    def __save(self, status: str, product: str, data: pd.DataFrame, use_mtime=False) -> DataStepFrame:
        assert isinstance(data, pd.DataFrame)
        data_file_path = self.metadata.token_as_path(product)

        self.save_to_featured_file(data, data_file_path)

        method = MTIME if use_mtime else DIGEST
        dependencies = self._dependencies.get(product)
        data_structure_descriptor = self._create_data_structure_descriptor(data)
        self.metadata.update(method, product, dependencies, columns=data_structure_descriptor, rows=len(data))
        result = DataStepFrame(status=status, data=data, dependencies=dependencies, data_set=product)
        return result

    def __read_file(self, product: str, source_item: str) -> DataStepFrame:
        self.metadata.is_updated(product)

        if source_item is not None:
            assert isinstance(source_item, str)
            self.metadata.is_updated(source_item)
            self.metadata.is_dependent(product, source_item)

        predecessor_item = self._dependencies_stack[-1]
        if predecessor_item != product:
            raise RuntimeError(
                "DATA_STEP stack mismatch while reading cache: "
                f"expected product={product!r} on top, got {predecessor_item!r}, "
                f"stack={self._dependencies_stack!r}. "
                "Zwykle po przerwanym runie Streamlit — zrestartuj appkę "
                "(init_steps czyści stos przy kolejnym starcie)."
            )
        # data_file_path = self.get_absolute_file_path(product)
        data_file_path = self.metadata.token_as_path(product)
        data = self.read_featured_file(data_file_path)

        result = DataStepFrame(status=CACHED, data_set=product, data=data)

        self._add_dependent(predecessor_item, product)
        return result

    def _add_dependent(self, item: str, value: str) -> None:
        self.is_initialised()
        assert value is not None
        assert isinstance(value, str)
        if value == item:
            return

        token = self.metadata.as_token(value)
        self._dependencies.update(item, token)
        return

    def _dependency_create(self, item: str) -> str:
        self.is_initialised()
        assert isinstance(item, str)
        token = self.metadata.as_token(item)
        self._dependencies.create(token)
        return token
