# -*- coding: utf-8 -*-
"""Runtime pool_id dla kont ROR (typ=ror) na podstawie RODZAJ* + waluta."""
from __future__ import annotations

import pandas as pd

from importers.assets.data_model import AssetsFile, KindDomain, TypeDomain

MBANK_PLN = "mbank_pln"
MBANK_EUR = "mbank_eur"
REVOLUT_PLN = "revolut_pln"
REVOLUT_EUR = "revolut_eur"

POOL_IDS = (MBANK_EUR, MBANK_PLN, REVOLUT_EUR, REVOLUT_PLN)
POOL_ID_COLUMN = "pool_id"


def resolve_pool_id(kind: object, currency: object) -> str | None:
    kind_text = "" if kind is None or (isinstance(kind, float) and pd.isna(kind)) else str(kind).strip()
    currency_text = (
        ""
        if currency is None or (isinstance(currency, float) and pd.isna(currency))
        else str(currency).strip().upper()
    )
    if not kind_text or not currency_text:
        return None

    if kind_text.startswith(KindDomain.MBANK):
        if currency_text == "PLN":
            return MBANK_PLN
        if currency_text == "EUR":
            return MBANK_EUR
        return None

    if kind_text.startswith(KindDomain.REVOLUT):
        if currency_text == "PLN":
            return REVOLUT_PLN
        if currency_text == "EUR":
            return REVOLUT_EUR
        return None

    return None


def assign_pool_id(assets: pd.DataFrame) -> pd.DataFrame:
    """Dodaje kolumnę pool_id. Każdy typ=ror musi dostać wartość z POOL_IDS."""
    result = assets.copy()
    result[POOL_ID_COLUMN] = ""

    if result.empty:
        return result

    is_ror = result[AssetsFile.TYPE].astype(str).str.strip() == TypeDomain.CURRENT_ACCOUNT
    unresolved: list[str] = []

    for idx in result.index[is_ror]:
        pool_id = resolve_pool_id(
            result.at[idx, AssetsFile.KIND],
            result.at[idx, AssetsFile.CURRENCY],
        )
        if pool_id is None or pool_id not in POOL_IDS:
            asset_id = result.at[idx, AssetsFile.ID]
            kind = result.at[idx, AssetsFile.KIND]
            currency = result.at[idx, AssetsFile.CURRENCY]
            unresolved.append(f"id={asset_id!r} KIND={kind!r} waluta={currency!r}")
            continue
        result.at[idx, POOL_ID_COLUMN] = pool_id

    if unresolved:
        details = "; ".join(unresolved)
        raise ValueError(
            "Brak mapowania pool_id dla kont typ=ror "
            f"(oczekiwane KIND mbank.*/revolut.* + waluta PLN/EUR): {details}"
        )

    return result
