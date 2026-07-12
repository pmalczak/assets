# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

import pandas as pd

from app_proc.data_root import get_online_data_root
from data_step.data_step import DATA_STEP
from importers.assets.data_model import AssetsDef, KindDomain
from importers.assets.read_assets import read_assets
from importers.mbank.data_model import MBankFile
from importers.mbank.read_m_transactions import read_m_transactions
from importers.revolut.read_r_deposits import read_revolut_deposit_transactions
from importers.revolut.read_r_transactions import read_revolut_account_transactions
from importers.revolut.revolut_account_file import RevolutAccountFile
from importers.revolut.revolut_deposit_file import RevolutDepositFile

SEARCH_TEXT_COLUMNS = ["opis", "tytul", "kontrahent", "konto"]
RESULT_COLUMNS = [
    "asset_id",
    "asset_opis",
    "zrodlo",
    "data",
    "kwota",
    "saldo",
    "opis",
    "tytul",
    "kontrahent",
    "konto",
    "dopasowane_pola",
]

MBANK_TEXT_COLUMNS = [
    MBankFile.MBANK_DESCRIPTION,
    MBankFile.MBANK_TITLE,
    MBankFile.MBANK_TRANSACTION_PARTY,
    MBankFile.MBANK_ACCOUNT_NUMBER,
]

REVOLUT_ACCOUNT_TEXT_COLUMNS = [
    RevolutAccountFile.KIND,
    RevolutAccountFile.PRODUCT,
    RevolutAccountFile.DESCRIPTION,
]

REVOLUT_DEPOSIT_TEXT_COLUMNS = [
    RevolutDepositFile.PRODUCT_NAME,
    RevolutDepositFile.DESCRIPTION,
]


def init_data_step() -> None:
    local_data_steps_root = Path(__file__).resolve().parent.parent
    DATA_STEP.init_steps(root=local_data_steps_root)


def load_all_transactions(
    data_root: Path | None = None,
    assets: pd.DataFrame | None = None,
) -> pd.DataFrame:
    init_data_step()
    if data_root is None:
        data_root = get_online_data_root()
    if assets is None:
        assets = read_assets()

    frames: list[pd.DataFrame] = []
    for _, asset_row in assets.iterrows():
        kind = asset_row.get(AssetsDef.KIND)
        if pd.isna(kind):
            continue

        asset_id = str(asset_row[AssetsDef.ID])
        asset_opis = "" if pd.isna(asset_row.get(AssetsDef.DESCR)) else str(asset_row[AssetsDef.DESCR])
        kind = str(kind)

        if kind.startswith(KindDomain.MBANK):
            raw = read_m_transactions(data_root, asset_id)
            if not raw.empty:
                frames.append(_normalize_mbank(raw, asset_id, asset_opis))
        elif kind.startswith(KindDomain.REVOLUT):
            input_path = data_root / asset_id
            account = read_revolut_account_transactions(input_path, asset_id)
            if not account.empty:
                frames.append(_normalize_revolut_account(account, asset_id, asset_opis))
            deposits = read_revolut_deposit_transactions(input_path, asset_id)
            if not deposits.empty:
                frames.append(_normalize_revolut_deposit(deposits, asset_id, asset_opis))

    if not frames:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    result = pd.concat(frames, ignore_index=True)
    return result[RESULT_COLUMNS]


def search_transactions(
    transactions: pd.DataFrame,
    query: str,
    *,
    case_sensitive: bool = False,
) -> pd.DataFrame:
    query = query.strip()
    if not query or transactions.empty:
        return transactions.iloc[0:0].copy()

    mask = _build_search_mask(transactions, query, case_sensitive=case_sensitive)
    result = transactions.loc[mask].copy()
    if result.empty:
        return result

    result["dopasowane_pola"] = result.apply(
        lambda row: _matched_fields(row, query, case_sensitive=case_sensitive),
        axis=1,
    )
    return result.sort_values(["data", "asset_id"], ascending=[False, True], ignore_index=True)


def _build_search_mask(
    df: pd.DataFrame,
    query: str,
    *,
    case_sensitive: bool,
) -> pd.Series:
    needle = query if case_sensitive else query.casefold()
    mask = pd.Series(False, index=df.index)
    for column in SEARCH_TEXT_COLUMNS:
        if column not in df.columns:
            continue
        series = df[column].astype("string").fillna("")
        if not case_sensitive:
            series = series.str.casefold()
        mask |= series.str.contains(needle, regex=False, na=False)
    return mask


def _matched_fields(row: pd.Series, query: str, *, case_sensitive: bool) -> str:
    needle = query if case_sensitive else query.casefold()
    matched: list[str] = []
    for column in SEARCH_TEXT_COLUMNS:
        value = row.get(column)
        if pd.isna(value):
            continue
        haystack = str(value) if case_sensitive else str(value).casefold()
        if needle in haystack:
            matched.append(column)
    return ", ".join(matched)


def _normalize_mbank(df: pd.DataFrame, asset_id: str, asset_opis: str) -> pd.DataFrame:
    result = pd.DataFrame(
        {
            "asset_id": asset_id,
            "asset_opis": asset_opis,
            "zrodlo": "mbank",
            "data": df[MBankFile.MBANK_TRANSACTION_DATE],
            "kwota": df[MBankFile.MBANK_AMOUNT],
            "saldo": df[MBankFile.MBANK_OUTSTANDING_BALANCE],
            "opis": df[MBankFile.MBANK_DESCRIPTION],
            "tytul": df[MBankFile.MBANK_TITLE],
            "kontrahent": df[MBankFile.MBANK_TRANSACTION_PARTY],
            "konto": df[MBankFile.MBANK_ACCOUNT_NUMBER],
            "dopasowane_pola": "",
        }
    )
    return result


def _normalize_revolut_account(df: pd.DataFrame, asset_id: str, asset_opis: str) -> pd.DataFrame:
    result = pd.DataFrame(
        {
            "asset_id": asset_id,
            "asset_opis": asset_opis,
            "zrodlo": "revolut-konto",
            "data": df[RevolutAccountFile.DATE],
            "kwota": df[RevolutAccountFile.AMOUNT],
            "saldo": df[RevolutAccountFile.BALANCE],
            "opis": df[RevolutAccountFile.DESCRIPTION],
            "tytul": df[RevolutAccountFile.KIND],
            "kontrahent": df[RevolutAccountFile.PRODUCT],
            "konto": "",
            "dopasowane_pola": "",
        }
    )
    return result


def _normalize_revolut_deposit(df: pd.DataFrame, asset_id: str, asset_opis: str) -> pd.DataFrame:
    money_in = pd.to_numeric(df[RevolutDepositFile.MONEY_IN], errors="coerce").fillna(0)
    money_out = pd.to_numeric(df[RevolutDepositFile.MONEY_OUT], errors="coerce").fillna(0)
    amount = money_in.where(money_in != 0, -money_out)

    result = pd.DataFrame(
        {
            "asset_id": asset_id,
            "asset_opis": asset_opis,
            "zrodlo": "revolut-depozyt",
            "data": df[RevolutDepositFile.DATE],
            "kwota": amount,
            "saldo": df[RevolutDepositFile.BALANCE],
            "opis": df[RevolutDepositFile.DESCRIPTION],
            "tytul": df[RevolutDepositFile.PRODUCT_NAME],
            "kontrahent": "",
            "konto": "",
            "dopasowane_pola": "",
        }
    )
    return result
