# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from data_root import get_online_data_root
from importers.revolut.revolut_account_file import RevolutAccountFile
from importers.revolut.revolut_deposit_file import RevolutDepositFile
from maintenance.move_mbank_files import move_mbank_files

pd.options.mode.copy_on_write = True
pd.options.future.infer_string = True


def move_revolut_files(file_owner: str):
    dropbox_assets = Path().home() / 'Dropbox/INWESTYCJE/assets'
    assert dropbox_assets.is_dir()

    assert file_owner in ('p_re', 'g_re')

    files = dropbox_assets.glob('*.csv')
    for file in files:
        fname = file.stem.split('_')
        if fname[0] == 'account-statement':
            _move_file(file, file_owner, dropbox_assets, 'account')

        elif fname[0] == 'trading-account-statement':
            continue

        elif len(fname) == 1:
            _move_file(file, file_owner, dropbox_assets, 'deposit')

        else:
            raise ValueError(fname[0])
    return


def _move_file(file: Path, file_owner: str, dropbox_assets: Path, type: str):
    df = pd.read_csv(file)
    if type == 'deposit':
        df = RevolutDepositFile.normalize_dtypes(df)
        RevolutDepositFile.check_structure(df)
    elif type == 'account':
        RevolutAccountFile.check_structure(df)
    else:
        raise ValueError(type)

    currency = get_account_currency(df)
    target = dropbox_assets / f'{file_owner}_{currency}' / file.name
    file.rename(target)
    print(f'PLIK:{file} przeniesiony')


def get_account_currency(df: pd.DataFrame) -> str:
    result = df[RevolutAccountFile.CURRENCY].unique().tolist()
    assert len(result) == 1
    result = result[0].lower()
    return result



if __name__ == '__main__':
    data_root = get_online_data_root()
    download = Path().home() / 'Downloads'
    assert download.is_dir()

    move_revolut_files('p_re')
    move_mbank_files(data_root, download)
    move_mbank_files(data_root, data_root)
