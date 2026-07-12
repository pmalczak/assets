# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"
from pathlib import Path


class GetAppPathError(Exception):
    pass


class AppFile:
    def __init__(self, app: str, reference=None):
        self.app_path = get_app_path(app, reference=reference)

    def get_path(self, file: str) -> Path:
        result = self.app_path / file
        return result

    def extend_path(self, path: str) -> Path:
        _path_chunks = path.split('/')
        result = self.app_path
        for path in _path_chunks:
            result /= path
            if not result.is_dir():
                result.mkdir()
        return result

    def get_str_path(self, file: str):
        return str(self.get_path(file))

    def create_missing_catalogs(self, dir):
        if isinstance(dir, Path):
            _app = self.app_path
            assert str(dir).startswith(str(_app))
            assert _app.is_dir()

            app_len = len(_app.parts)
            missing = dir.parts[app_len:]

            for subpath in missing:
                _app /= subpath
                if not _app.is_dir():
                    _app.mkdir()
            assert dir.is_dir()
        else:
            raise AttributeError
        return


def _resolve_reference(reference):
    if reference is None:
        reference = Path('.')
    elif isinstance(reference, str):
        reference = Path(reference)

    reference = reference.resolve()
    if reference.is_file():
        result = reference.parent
    elif reference.is_dir():
        result = reference
    else:
        raise ValueError
    return result


def get_app_path(app: str, reference=None) -> Path:

    max_levels = 6

    _reference_ = _resolve_reference(reference)

    for level in range(0, max_levels):
        try:
            result = _get_app_path(app, _reference_)
            return result
        except KeyError:
            _reference_ = _reference_.parent

    msg = f'brak katalogu "{app}" w ścieżce "{reference}"'
    raise GetAppPathError(msg)


def _get_app_path(app: str, reference: Path) -> Path:
    assert isinstance(reference, Path)
    reference /= app
    if not reference.is_dir():
        raise KeyError
    return reference


def output_directory(file_name: str = None) -> Path:
    assert file_name is None or isinstance(file_name, str)
    result = AppFile('dist').get_path('../static')
    if file_name is not None:
        result /= file_name
    result = result.resolve()
    return result
