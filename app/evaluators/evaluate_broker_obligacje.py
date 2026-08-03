# -*- coding: utf-8 -*-
"""Snapshot BROKER obligacje skarbowe: 1 wiersz = Σ WARTOŚĆ AKTUALNA z najnowszego stanu."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from app_proc.data_root import resolve_asset_dir
from evaluators.valuation_date import format_date_columns
from importers.assets.data_model import AssetsDef, GroupDomain, TypeDomain
from importers.pkobp.data_model import PkoBpStan
from importers.pkobp.read_stan import read_obligacje_stan, select_stan_as_of, stan_mtm_total

DEFAULT_BONDS_BROKER_ID = "obligacjeskarbowe"


def evaluate_broker_obligacje(
    data_root: Path,
    asset_id: str,
    assets_file_row: pd.Series,
    valuation_date: date,
) -> tuple[pd.DataFrame, list[str]]:
    p = resolve_asset_dir(asset_id, assets_file_row[AssetsDef.TYPE])
    if not p.is_dir():
        raise ValueError(p)

    warnings: list[str] = []
    stan_df = read_obligacje_stan(p, asset_id)
    stan_as_of = select_stan_as_of(stan_df, valuation_date)
    if stan_as_of.empty:
        warnings.append(f"Brak StanRachunkuRejestrowego ≤ {valuation_date.isoformat()}")
        return pd.DataFrame(columns=list(AssetsDef.expected_columns())), warnings

    total = stan_mtm_total(stan_as_of)
    n_pos = len(stan_as_of)
    eval_date = str(stan_as_of[PkoBpStan.FILE_DATE].iloc[0])

    row = AssetsDef.as_assets_row(assets_file_row)
    row[AssetsDef.VALUE] = float(total)
    row[AssetsDef.EVALUATION_DATE] = eval_date
    row[AssetsDef.TYPE] = TypeDomain.BONDS
    row[AssetsDef.GROUP] = GroupDomain.INVESTMENT
    base_descr = str(assets_file_row.get(AssetsDef.DESCR) or asset_id).strip() or asset_id
    row[AssetsDef.DESCR] = f"{base_descr} ({n_pos} poz.)"

    result = pd.DataFrame([row])
    AssetsDef.check_structure(result)
    return format_date_columns(result, AssetsDef.EVALUATION_DATE), warnings


def is_obligacje_broker(assets_file_row: pd.Series) -> bool:
    typ = str(assets_file_row.get(AssetsDef.TYPE) or "")
    asset_id = str(assets_file_row.get(AssetsDef.ID) or "")
    return typ == TypeDomain.BONDS or asset_id == DEFAULT_BONDS_BROKER_ID
