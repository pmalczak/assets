# -*- coding: utf-8 -*-
from __future__ import annotations

__author__ = "pmalczak@gmail.com"

from contextlib import contextmanager
from pathlib import Path
import json
import os
import sys
import tempfile

from utils.get_app_path import AppFile, GetAppPathError

HOME_PATH = '$HOME_PATH'
DIR_TOKEN = 'DIR:'
DEPENDENCIES = 'dependencies'
METADATA_FILE_NAME = '_metadata.json'
METADATA_LOCK_NAME = '_metadata.lock'


def _lock_exclusive(lock_fp) -> None:
    if sys.platform == "win32":
        import msvcrt
        lock_fp.seek(0)
        if lock_fp.read(1) == "":
            lock_fp.write("0")
            lock_fp.flush()
        lock_fp.seek(0)
        msvcrt.locking(lock_fp.fileno(), msvcrt.LK_LOCK, 1)
        return
    import fcntl
    fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX)


def _unlock(lock_fp) -> None:
    if sys.platform == "win32":
        import msvcrt
        lock_fp.seek(0)
        msvcrt.locking(lock_fp.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl
    fcntl.flock(lock_fp.fileno(), fcntl.LOCK_UN)


class MetadataPrimitives:
    def __init__(self, metadata_root: Path, **kwargs):
        assert metadata_root.is_dir()

        if not metadata_root.exists():
            metadata_root.mkdir()
        self._metadata_path = metadata_root

        self._metadata_file = self._metadata_path / METADATA_FILE_NAME
        self._lock_file = self._metadata_path / METADATA_LOCK_NAME
        self._home = str(Path().home())

        with self._exclusive_metadata_lock():
            self._reload_metadata_unlocked()

    def set_metadata(self, metadata):
        self._metadata = metadata

    def get_metadata_root(self):
        return self._metadata_path

    @staticmethod
    def _get_metadata_file(data_cache, reference=None) -> AppFile:
        try:
            app_file = AppFile(data_cache, reference=reference)
        except GetAppPathError:
            dist_dir = AppFile('dist').app_path
            cache_dir = dist_dir / '..' / data_cache
            cache_dir = os.path.realpath(cache_dir)
            os.mkdir(cache_dir)
            print(f'fixed: {data_cache} created')
            app_file = AppFile(data_cache)
        return app_file

    def get_app_path(self):
        return self._app_file.app_path

    def get_metadata(self):
        return self._metadata

    @contextmanager
    def _exclusive_metadata_lock(self):
        """Exclusive lock on sidecar lock file (serializes read-modify-write)."""
        self._metadata_path.mkdir(parents=True, exist_ok=True)
        with open(self._lock_file, 'a+', encoding='utf-8') as lock_fp:
            _lock_exclusive(lock_fp)
            try:
                yield
            finally:
                _unlock(lock_fp)

    def _reload_metadata_unlocked(self) -> None:
        try:
            with open(self._metadata_file, 'rt', encoding='utf-8') as f:
                self._metadata = json.load(f)
        except FileNotFoundError:
            self._metadata = {}

    def _dump_metadata_unlocked(self) -> None:
        """Atomowy zapis: temp w tym samym katalogu + os.replace."""
        dump = json.dumps(self._metadata, indent=4)
        fd, tmp_name = tempfile.mkstemp(
            prefix='_metadata.',
            suffix='.json.tmp',
            dir=str(self._metadata_path),
        )
        try:
            with os.fdopen(fd, 'wt', encoding='utf-8') as fp:
                fp.write(dump)
                fp.flush()
                os.fsync(fp.fileno())
            os.replace(tmp_name, self._metadata_file)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def dump_metadata(self, backup: str = '') -> None:
        with self._exclusive_metadata_lock():
            self._dump_metadata_unlocked()
            if backup:
                backup_path = self._metadata_path / backup
                backup_path.write_text(
                    json.dumps(self._metadata, indent=4),
                    encoding='utf-8',
                )

    def as_token(self, resource: str) -> str:
        if isinstance(resource, str):
            if resource.startswith(self._home):
                p = Path(resource)
                resource = resource.replace(self._home, HOME_PATH)
                if p.is_file():
                    pass
                elif p.is_dir():
                    resource = DIR_TOKEN + resource
                else:
                    raise ValueError(resource)

            return resource
        else:
            raise NotImplementedError

    def update_item_descriptor(self, resource, item_descriptor):
        item = self.as_token(resource)

        _dependencies = item_descriptor[DEPENDENCIES]
        for dep in _dependencies:
            if dep.startswith(self._home):
                m = f'not really an item: {dep}'
                raise AssertionError(m)

        with self._exclusive_metadata_lock():
            self._reload_metadata_unlocked()
            self._metadata[item] = item_descriptor
            self._dump_metadata_unlocked()

    def get_items_descriptor(self, resource) -> dict:
        _metadata = self.get_metadata()
        _key = self.as_token(resource)
        data_set_descriptor = _metadata[_key]
        return data_set_descriptor

    def is_dir_token(self, resource):
        return resource.startswith(DIR_TOKEN)

    def token_as_path(self, token: str) -> Path:
        if not isinstance(token, str):
            raise NotImplementedError

        if self.is_dir_token(token):
            token = token.split(DIR_TOKEN)
            token = token[1]
            result = token.replace(HOME_PATH, self._home)
            result = Path(result)
            # Brak katalogu (np. po migracji assets→cash_pool) obsługuje is_updated → MetadataUpdateError.

        elif token.startswith(HOME_PATH):
            result = token.replace(HOME_PATH, self._home)
            result = Path(result)

        else:
            result = self._metadata_path / token
        return result
