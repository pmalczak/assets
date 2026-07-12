# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"
from pathlib import Path
import json
import os

from utils.get_app_path import AppFile, GetAppPathError

HOME_PATH = '$HOME_PATH'
DIR_TOKEN = 'DIR:'
DEPENDENCIES = 'dependencies'


class MetadataPrimitives:
    def __init__(self, metadata_root: Path, **kwargs):
        assert metadata_root.is_dir()

        if not metadata_root.exists():
            metadata_root.mkdir()
        self._metadata_path = metadata_root

        self._metadata_file = self._metadata_path / '_metadata.json'
        self._home = str(Path().home())

        try:
            with open(self._metadata_file, 'rt') as f:
                metadata = json.load(f)
        except FileNotFoundError:
            metadata = {}
        self._metadata = metadata

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

    def dump_metadata(self, backup=''):
        dump = json.dumps(self._metadata, indent=4)
        with open(self._metadata_file / backup, 'wt') as fp:
            fp.write(dump)

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
        _metadata = self.get_metadata()
        item = self.as_token(resource)

        _dependencies = item_descriptor[DEPENDENCIES]
        for resource in _dependencies:
            if resource.startswith(self._home):
                m = f'not really an item: {resource}'
                raise AssertionError(m)

        _metadata[item] = item_descriptor
        self.dump_metadata()
        return

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
            assert result.is_dir()

        elif token.startswith(HOME_PATH):
            result = token.replace(HOME_PATH, self._home)
            result = Path(result)

        else:
            result = self._metadata_path / token
        return result
