# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

from maintenance.move_downloaded_results import ACTION_MOVED, KIND_MBANK, MoveResult


def get_downloaded(download) -> list:
    lst = download.glob('*_*_*.csv')
    lst = filter(lambda x: len(x.stem) == 22, lst)
    lst = list(lst)
    return lst


def move_mbank_files(cash_pool_root, download) -> list[MoveResult]:
    target_dirs = get_target_dirs(cash_pool_root)
    lst = get_downloaded(download)

    results: list[MoveResult] = []
    for f in lst:
        results.append(move_file(f, cash_pool_root, target_dirs))
    return results


def get_target_dirs(cash_pool_root: Path) -> dict:
    result = cash_pool_root.glob('*')
    result = filter(lambda x: x.is_dir(), result)
    result = map(lambda x: x.name, result)
    result = map(lambda x: x.split('_'), result)
    result = filter(lambda x: len(x) >= 4, result)
    result = map(lambda x: ('_'.join(x), x[3]), result)
    result = list(result)
    result = {v: k for k, v in result}
    return result


def account_key_from_stem(stem: str) -> str:
    """Ostatnie 4 znaki pierwszego segmentu nazwy wyciągu mBank (`XXXXXXXX_od_do`)."""
    segments = stem.split('_')
    if len(segments) != 3:
        raise ValueError(stem)
    key = segments[0]
    if len(key) != 8:
        raise ValueError(stem)
    return key[4:]


def move_file(f: Path, cash_pool_root, target_dirs: dict) -> MoveResult:
    key = account_key_from_stem(f.stem)
    if key not in target_dirs:
        known = ", ".join(sorted(target_dirs)) or "(brak)"
        raise ValueError(
            f"Brak katalogu w cash_pool dla rachunku mBank …{key} "
            f"(plik: {f.name}). Oczekiwany katalog z 4. segmentem '{key}' "
            f"(np. p_m_XX_{key}). Znane rachunki: {known}."
        )
    target_dir = cash_pool_root / target_dirs[key]
    dst = target_dir / f.name
    f.replace(dst)
    return MoveResult(source=f, destination=dst, action=ACTION_MOVED, kind=KIND_MBANK)
