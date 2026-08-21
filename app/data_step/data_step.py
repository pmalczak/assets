# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

import pandas as pd
from pathlib import Path

from .data_step_dependencies import Dependencies
from .data_step_primitives import DataStepPrimitives
from .data_step_frame import DataStepFrame
from .metadata_class import DIGEST, Metadata
from .data_strep_data_types import REFRESHED


class DataStep(DataStepPrimitives):  # interface class
    def __init__(self, data_steps: str = 'data_steps', meta_parameters: str = ''):
        super(DataStep, self).__init__(data_steps, meta_parameters)

    def init_steps(self, root: Path = None):
        assert root is not None

        data_steps_root = self.find_data_step_root(start=root)
        if self._initialised and self._data_steps_root == data_steps_root:
            # Streamlit / przerwany run: ten sam root, ale stos mógł zostać brudny.
            self._reset_dependency_stack()
            self._dependencies = Dependencies()
            return

        self._data_steps_root = data_steps_root
        self.metadata = Metadata(data_steps_root)
        self._reset_dependency_stack()
        self._dependencies = Dependencies()
        self._cache = {}
        self._initialised = True

    def force_read_data(self) -> None:
        self.is_initialised()
        self.metadata.force_read_data(True)

    def invalidate(self, product: str) -> None:
        """Usuwa produkt z DATA_STEP (metadata, plik, RAM) — następny ``obtain`` przebuduje."""
        self.is_initialised()
        assert isinstance(product, str)
        self._cache.pop(product, None)
        self.metadata.updated_stat_cache.pop(product, None)
        path = self.metadata.token_as_path(product)
        self.metadata.delete(product)
        if path.is_file():
            path.unlink()

    def obtain(self,
               product: str,
               data_collector,
               input_data_set: (str, Path, dict) = None,
               keep_cached=False,
               **kwargs) -> DataStepFrame:
        """Buduje lub odczytuje produkt pośredni w ``data_steps``.

        Zależności powstają **pośrednio** — bez wskazywania zewnętrznego pliku
        lub katalogu źródłowego:

        * zagnieżdżone wywołania ``obtain`` / ``obtain_dependent`` (stos
          ``_dependencies_stack`` — rodzic rejestruje produkt potomny),
        * argumenty typu ``DataStepFrame`` przekazane w ``**kwargs``.

        Parametr ``input_data_set`` jest opcjonalny i zwykle używany wewnętrznie
        przez ``obtain_dependent``; bezpośrednie użycie w kodzie aplikacji
        nie jest zalecane.

        Typowe zastosowanie: kroki potoku (np. snapshot portfela), które
        składają wynik z innych produktów ``data_steps`` już zarejestrowanych
        w grafie zależności.

        Args:
            product: Token produktu w ``data_steps`` (np. ``ASSETS_SNAPSHOT_STEP/2026-01-01.parquet``).
            data_collector: Callable zwracający ``DataFrame`` (lub ``DataStepFrame``).
            input_data_set: Opcjonalny token źródła — preferuj ``obtain_dependent``.
            keep_cached: Trzymaj wynik w pamięci między wywołaniami.
            **kwargs: Dodatkowe argumenty przekazywane do ``data_collector``.
                Wartości ``DataFrame`` w kwargs nie są rejestrowane jako zależności
                (wypisywane jest ostrzeżenie).
        """
        self.is_initialised()
        assert isinstance(product, str)
        for k, v in kwargs.items():
            if isinstance(v, pd.DataFrame):
                print(f'possibly lost dependency for {product} -> arg: {k}')

        self._ensure_dependency_stack()
        self._dependency_create(product)
        if input_data_set:
            self._add_dependent(product, input_data_set)
        prev = self._dependencies_stack[-1]
        self._dependencies_stack.append(product)
        try:
            self._add_arguments_to_dependencies(product, **kwargs)
            result = self._obtain_from_cache_or_collect(data_collector, product,
                                                        input_data_set, keep_cached, **kwargs)
        except Exception as e:
            try:
                self.metadata.delete(product)
            except KeyError:
                pass
            raise e
        finally:
            last_element = self._pop_dependency_frame(product)
        self._add_dependent(prev, product)
        if last_element != product:
            raise RuntimeError(
                f"DATA_STEP stack mismatch while finishing obtain({product!r}): "
                f"popped {last_element!r}, remaining stack={self._dependencies_stack!r}"
            )
        return result

    def obtain_dependent(self,
                         product: str,
                         data_collector,
                         input_item: (str, Path),
                         keep_cached: bool = False,
                         **kwargs) -> DataStepFrame:
        """Buduje lub odczytuje produkt w ``data_steps`` z **jawnie wskazanego**
        pliku lub katalogu źródłowego.

        ``input_item`` może leżeć poza ``data_steps`` (np. plik Excel w Dropboxie
        lub katalog z wyciągami CSV). Ścieżka jest rejestrowana w metadanych
        jako zależność produktu, a collector otrzymuje ją jako ``source_file``.

        Po odświeżeniu produktu aktualizowany jest digest źródła, dzięki czemu
        cache invaliduje się po zmianie pliku/katalogu wejściowego.

        Typowe zastosowanie: import z pliku zewnętrznego do parquet w
        ``data_steps`` (wyciągi bankowe, konfiguracja aktywów, plik reguł ROI).

        Args:
            product: Token produktu docelowego w ``data_steps``.
            data_collector: Callable przyjmujący ``source_file`` (``Path``).
            input_item: Plik lub katalog źródłowy (``str`` lub ``Path``).
            keep_cached: Trzymaj wynik w pamięci między wywołaniami.
            **kwargs: Dodatkowe argumenty przekazywane do ``data_collector``.
        """
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
