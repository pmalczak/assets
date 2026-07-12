from pathlib import Path
import datetime

import pandas as pd
from .nbp_fx_file_cache import NbpFxFileCache

NBP_API_PLN = 'PLN'
NBP_API_EUR = 'EUR'
NBP_API_HUF = 'HUF'
NBP_API_USD = 'USD'


class NbpFxRepository:
    def __init__(self, target_directory: Path = None, min_year=2017):
        assert isinstance(target_directory, Path)
        if not target_directory.is_dir():
            raise NotADirectoryError(target_directory)
        self.target_directory = target_directory
        self.min_year = min_year

    def update_to_date(self):
        today = datetime.datetime.today()
        result = []
        for year in range(self.min_year, today.year + 1):
            try:
                c = NbpFxFileCache(self.target_directory, year, delete_outdated_cache_files=True)
                r = c.df()
                result += [r]
            except ReferenceError as e:
                continue
        result = pd.concat(result)
        return result
