# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

import hashlib
import os
from pathlib import Path

from data_step.metadata_primitives_class import (
    DEPENDENCIES,
    DEPENDENCY_DIGESTS,
    MetadataPrimitives,
)

DATA_FRAME_ROWS = 'data_frame_rows'
MTIME = 'mtime'
DIGEST = 'digest'
COLUMNS = 'columns'


class MetadataUpdateError(Exception):
    pass


class Metadata(MetadataPrimitives):
    def __init__(self, root: Path):
        super().__init__(root)

        self.force_update = False
        self.cached_data_types = ('.parquet', )
        self.updated_stat_cache = {}

    def is_updated(self, token: str) -> None:
        assert isinstance(token, str)
        if self.force_update:
            raise MetadataUpdateError(f'forced data reading')

        if token in self.updated_stat_cache:
            if not self._cached_token_still_valid(token):
                del self.updated_stat_cache[token]
            else:
                return

        data_file_path = self.token_as_path(token)
        if self.is_dir_token(token):
            if not data_file_path.is_dir():
                raise MetadataUpdateError(f"dir doesn't exists {token}")

        elif not data_file_path.is_file():
            raise MetadataUpdateError(f"file doesn't exists {token}")

        self._is_object_up_to_date(token)
        self._all_dependencies_are_up_to_date(token)
        self.updated_stat_cache[token] = None
        return

    # def create_missing_catalogs(self, item_path: Path) -> None:
    #     _, ext = os.path.splitext(item_path.name)
    #     if ext in self.cached_data_types:  # if it's cached
    #         self._app_file.create_missing_catalogs(item_path.parent)
    #     return

    def update(self,
               method: str,
               token: str,
               dependencies: list,
               columns: (str, list, tuple) = None,
               rows: int = None,
               ) -> None:
        item_path = self.token_as_path(token)
        # self.create_missing_catalogs(item_path)

        try:
            item_descriptor = self.get_items_descriptor(token)
        except KeyError:
            item_descriptor = {}

        dependencies = [dep for dep in (dependencies or []) if dep != token]
        item_descriptor[DEPENDENCIES] = dependencies
        assert token not in dependencies
        dir_dep_digests = self._dir_dependency_digests(dependencies)
        if dir_dep_digests:
            item_descriptor[DEPENDENCY_DIGESTS] = dir_dep_digests
        else:
            item_descriptor.pop(DEPENDENCY_DIGESTS, None)
        if method == DIGEST:

            if self.is_dir_token(token):
                digest = self._calc_dir_token_digest(item_path)

            else:
                digest = self._calc_file_digest(item_path)

            item_descriptor[DIGEST] = digest
            if MTIME in item_descriptor:
                del item_descriptor[MTIME]
        elif method == MTIME:
            mtime = os.path.getmtime(item_path)
            item_descriptor[MTIME] = mtime
            if DIGEST in item_descriptor:
                del item_descriptor[DIGEST]

        if columns is not None:
            item_descriptor[COLUMNS] = columns

        if rows is not None:
            item_descriptor[DATA_FRAME_ROWS] = rows

        self.update_item_descriptor(token, item_descriptor)
        if token in self.updated_stat_cache:
            del self.updated_stat_cache[token]
        return

    def delete(self, missing_file):
        """Usuwa wpis z rejestru i atomowo zapisuje metadata (pod flock)."""
        self.delete_many([missing_file])

    def delete_many(self, missing_files: list[str]) -> None:
        """Jedna podmiana `_metadata.json` dla wielu wpisów (mniej wyścigów na Windowsie)."""
        tokens = [token for token in missing_files if token]
        if not tokens:
            return
        with self._exclusive_metadata_lock():
            self._reload_metadata_unlocked()
            changed = False
            for token in tokens:
                if token in self._metadata:
                    del self._metadata[token]
                    changed = True
            if changed:
                self._dump_metadata_unlocked()


    def force_read_data(self, value: bool) -> None:
        self.force_update = value

    def _is_object_up_to_date(self, token) -> None:
        # data_file_path = self.data_set_as_file_path(metadata_item)
        item_path = self.token_as_path(token)

        try:
            descriptor = self.get_items_descriptor(token)
        except KeyError:
            raise MetadataUpdateError(f"file's outdated {token}")

        if DIGEST in descriptor:

            if self.is_dir_token(token):
                digest = self._calc_dir_token_digest(item_path)

            elif not item_path.is_file():
                raise MetadataUpdateError(f"file's outdated {token}")

            elif item_path.is_file():
                digest = self._calc_file_digest(item_path)

            else:
                raise ValueError

            if descriptor[DIGEST] != digest:
                raise MetadataUpdateError(f"file's outdated {token}")
            return

        elif MTIME in descriptor:
            if not item_path.is_file():
                raise MetadataUpdateError(f"file's outdated {token}")
            mtime = os.path.getmtime(item_path)
            if descriptor[MTIME] != mtime:
                raise MetadataUpdateError(f"file's outdated {token}")
            return

        raise NotImplementedError

    def _cached_token_still_valid(self, token: str) -> bool:
        try:
            descriptor = self.get_items_descriptor(token)
        except KeyError:
            return False

        item_path = self.token_as_path(token)
        if self.is_dir_token(token):
            if not item_path.is_dir():
                return False
            return descriptor.get(DIGEST) == self._calc_dir_token_digest(item_path)
        if not item_path.is_file():
            return False
        dir_deps = [d for d in (descriptor.get(DEPENDENCIES) or []) if self.is_dir_token(d)]
        stored = descriptor.get(DEPENDENCY_DIGESTS) or {}
        if dir_deps and not stored:
            return False
        for dep, stored_digest in stored.items():
            try:
                if stored_digest != self._current_token_digest(dep):
                    return False
            except MetadataUpdateError:
                return False
        return True

    def _dir_dependency_digests(self, dependencies: list) -> dict:
        result = {}
        for dep in dependencies or []:
            if self.is_dir_token(dep):
                result[dep] = self._current_token_digest(dep)
        return result

    def _current_token_digest(self, token: str) -> str:
        item_path = self.token_as_path(token)
        if self.is_dir_token(token):
            if not item_path.is_dir():
                raise MetadataUpdateError(f"dir doesn't exists {token}")
            return self._calc_dir_token_digest(item_path)
        if not item_path.is_file():
            raise MetadataUpdateError(f"file doesn't exists {token}")
        return self._calc_file_digest(item_path)

    @staticmethod
    def _calc_dir_token_digest(item_path: Path) -> str:
        assert item_path.is_dir()
        parts = []
        for path in sorted(item_path.glob('*.*'), key=lambda p: p.name.lower()):
            if path.is_file():
                parts.append(f"{path.name}:{path.stat().st_size}")
        content = "\n".join(parts).encode("utf-8")
        md5hash = hashlib.md5()
        md5hash.update(content)
        return md5hash.hexdigest()

    @staticmethod
    def _calc_file_digest(item_path: Path) -> str:
        assert item_path.is_file()
        md5hash = hashlib.md5()
        with open(item_path, 'rb') as f:
            content = f.read()
        md5hash.update(content)
        digest = md5hash.hexdigest()
        return digest

    def _get_dependencies(self, resource: str) -> list:
        descriptor = self.get_items_descriptor(resource)
        dependencies = descriptor[DEPENDENCIES]
        return dependencies

    def is_dependent(self, product: str, input_: str) -> None:
        assert isinstance(product, str)
        assert isinstance(input_, str)
        input_item = self.as_token(input_)
        try:
            dependencies = self._get_dependencies(product)
        except KeyError:
            raise MetadataUpdateError(f"metadata missing for {product}")
        if input_item not in dependencies:
            raise MetadataUpdateError(f"{input_} doesn't exist in dependencies")
        return

    def _all_dependencies_are_up_to_date(self, resource: str) -> None:
        item = self.as_token(resource)
        msg = f"dependencies aren't updated {resource}"
        try:
            dependencies = self._get_dependencies(item)
        except KeyError:
            raise MetadataUpdateError(msg)

        self.check_cycles(item, dependencies)
        stored_dir_digests = self.get_items_descriptor(item).get(DEPENDENCY_DIGESTS) or {}
        for dep in dependencies:
            self.is_updated(dep)
            if not self.is_dir_token(dep):
                continue
            current = self._current_token_digest(dep)
            if stored_dir_digests.get(dep) != current:
                raise MetadataUpdateError(
                    f"dir dependency changed {resource} <- {dep}"
                )

    @staticmethod
    def check_cycles(resource, dependencies):
        for item in dependencies:
            if isinstance(item, str):
                if item == resource:
                    raise ValueError(resource)
