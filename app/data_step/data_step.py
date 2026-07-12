# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

import pandas as pd
from pathlib import Path

from .data_step_primitives import DataStepPrimitives
from .data_step_frame import DataStepFrame
from .metadata_class import DIGEST
from .data_strep_data_types import REFRESHED


class DataStep(DataStepPrimitives):  # interface class
    def __init__(self, data_steps: str = 'data_steps', meta_parameters: str = ''):
        super(DataStep, self).__init__(data_steps, meta_parameters)

    def force_read_data(self) -> None:
        self.is_initialised()
        self.metadata.force_read_data(True)

    def obtain(self,
               product: str,
               data_collector,
               input_data_set: (str, Path, dict) = None,
               keep_cached=False,
               **kwargs) -> DataStepFrame:
        self.is_initialised()
        assert isinstance(product, str)
        for k, v in kwargs.items():
            if isinstance(v, pd.DataFrame):
                print(f'possibly lost dependency for {product} -> arg: {k}')

        self._dependency_create(product)
        if input_data_set:
            self._add_dependent(product, input_data_set)
        prev = self._dependencies_stack[-1]
        self._dependencies_stack.append(product)
        self._add_arguments_to_dependencies(product, **kwargs)
        try:
            result = self._obtain_from_cache_or_collect(data_collector, product,
                                                        input_data_set, keep_cached, **kwargs)
        except Exception as e:
            try:
                self.metadata.delete(product)
                self.metadata.dump_metadata()
            except KeyError:
                pass
            raise e
        finally:
            last_element = self._dependencies_stack.pop()
        self._add_dependent(prev, product)
        assert last_element == product
        return result

    def obtain_dependent(self,
                         product: str,
                         data_collector,
                         input_item: (str, Path),
                         keep_cached: bool = False,
                         **kwargs) -> DataStepFrame:
        self.is_initialised()
        assert isinstance(product, str)
        assert isinstance(input_item, (str, Path))
        if isinstance(input_item, Path):
            input_item = str(input_item)

        token = self._dependency_create(input_item)

        result = self.obtain(product, data_collector, input_data_set=token, keep_cached=keep_cached, **kwargs)
        # result = self.obtain(product, data_collector, input_data_set=input_item, keep_cached=keep_cached, **kwargs)
        if result.get_status() == REFRESHED:
            self.metadata.update(DIGEST, token, [])
        return result


DATA_STEP = DataStep()
