# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from importers.revolut.revolut_account_file import RevolutAccountFile
from importers.revolut.revolut_deposit_file import RevolutDepositFile
from maintenance.move_downloaded_results import (
    ACTION_DELETED_EMPTY,
    ACTION_MOVED,
    ACTION_SKIPPED,
    KIND_REVOLUT,
    MoveResult,
)

download_dir = {'p_re': 'Dropbox/INWESTYCJE/download/pm',
                'g_re': 'Dropbox/INWESTYCJE/download/gm'}


def move_revolut_files(dropbox_assets, file_owner: str) -> list[MoveResult]:
    assert file_owner in ('p_re', 'g_re')

    download_assets = Path().home() / download_dir[file_owner]
    assert download_assets.is_dir()

    results: list[MoveResult] = []
    files = download_assets.glob('*.csv')
    for file in files:
        fname = file.stem.split('_')
        if fname[0] == 'account-statement':
            results.append(_move_file(file, file_owner, dropbox_assets, 'account'))

        elif fname[0] == 'trading-account-statement':
            results.append(
                MoveResult(
                    source=file,
                    destination=None,
                    action=ACTION_SKIPPED,
                    kind=KIND_REVOLUT,
                )
            )

        elif len(fname) == 1:
            results.append(_move_file(file, file_owner, dropbox_assets, 'deposit'))

        else:
            results.append(
                MoveResult(
                    source=file,
                    destination=None,
                    action=ACTION_SKIPPED,
                    kind=KIND_REVOLUT,
                )
            )
    return results


def _move_file(file: Path, file_owner: str, dropbox_assets: Path, type: str) -> MoveResult:
    df = pd.read_csv(file)
    if type == 'deposit':
        df = RevolutDepositFile.normalize_dtypes(df)
        df[RevolutDepositFile.FILE_DATE] = ''
        RevolutDepositFile.check_structure(df)
    elif type == 'account':
        df[RevolutAccountFile.FILE_DATE] = ''
        RevolutAccountFile.check_structure(df)
    else:
        raise ValueError(type)

    if df.empty:
        file.unlink()
        return MoveResult(
            source=file,
            destination=None,
            action=ACTION_DELETED_EMPTY,
            kind=KIND_REVOLUT,
        )

    currency = get_account_currency(df)
    target = dropbox_assets / f'{file_owner}_{currency}' / file.name
    file.rename(target)
    return MoveResult(
        source=file,
        destination=target,
        action=ACTION_MOVED,
        kind=KIND_REVOLUT,
    )


def get_account_currency(df: pd.DataFrame) -> str:
    result = df[RevolutAccountFile.CURRENCY].unique().tolist()
    assert len(result) == 1
    result = result[0].lower()
    return result
