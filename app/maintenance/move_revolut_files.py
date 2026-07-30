# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from app_proc.data_root import get_online_data_root
from importers.revolut.account_data_model import RevolutAccountFile
from importers.revolut.deposit_data_model import RevolutDepositFile
from maintenance.move_downloaded_results import (
    ACTION_DELETED_EMPTY,
    ACTION_MOVED,
    ACTION_SKIPPED,
    KIND_REVOLUT,
    MoveResult,
)

download_dir = {'p_re': 'Dropbox/INWESTYCJE/download/pm',
                'g_re': 'Dropbox/INWESTYCJE/download/gm'}

_TRADING_PREFIXES = ('trading-account-statement', 'trading-pnl-statement')


def broker_asset_id(file_owner: str) -> str:
    return f'{file_owner}_robo'


def move_revolut_files(
    dropbox_cash_pool,
    file_owner: str,
    assets_root: Path | None = None,
) -> list[MoveResult]:
    assert file_owner in ('p_re', 'g_re')

    download_assets = Path().home() / download_dir[file_owner]
    assert download_assets.is_dir()
    assets_root = assets_root or get_online_data_root()

    results: list[MoveResult] = []
    files = download_assets.glob('*.csv')
    for file in files:
        fname = file.stem.split('_')
        if fname[0] == 'account-statement':
            results.append(_move_file(file, file_owner, dropbox_cash_pool, 'account'))

        elif fname[0] in _TRADING_PREFIXES:
            results.append(_move_trading_file(file, file_owner, assets_root))

        elif len(fname) == 1:
            results.append(_move_file(file, file_owner, dropbox_cash_pool, 'deposit'))

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


def _move_trading_file(file: Path, file_owner: str, assets_root: Path) -> MoveResult:
    if _is_trading_file_empty(file):
        file.unlink()
        return MoveResult(
            source=file,
            destination=None,
            action=ACTION_DELETED_EMPTY,
            kind=KIND_REVOLUT,
        )

    target_dir = assets_root / broker_asset_id(file_owner)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / file.name
    file.rename(target)
    return MoveResult(
        source=file,
        destination=target,
        action=ACTION_MOVED,
        kind=KIND_REVOLUT,
    )


def _is_trading_file_empty(file: Path) -> bool:
    prefix = file.stem.split('_')[0]
    if prefix == 'trading-account-statement':
        df = pd.read_csv(file)
        return df.empty
    # PnL: sekcje + nagłówki bez wierszy danych (linia zaczynająca się od cyfry = data)
    text = file.read_text(encoding='utf-8-sig')
    return not any(line and line[0].isdigit() for line in text.splitlines())


def _move_file(file: Path, file_owner: str, dropbox_cash_pool: Path, type: str) -> MoveResult:
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
    target = dropbox_cash_pool / f'{file_owner}_{currency}' / file.name
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
