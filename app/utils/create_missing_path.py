# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

import os
from pathlib import Path


def create_missing_paths(_path: Path):
    if _path.is_file():
        return

    if not _path.parent.is_dir():
        create_missing_paths(_path.parent)

    if not _path.is_dir():
        os.mkdir(_path)
    return
