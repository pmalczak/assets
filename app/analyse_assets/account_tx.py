# -*- coding: utf-8 -*-
"""Wspólny model transakcji konta ROR (pool) — niezależny od formatu banku."""
from __future__ import annotations

import pandas as pd

from importers.mbank.data_model import MBankFile
from importers.revolut.account_data_model import RevolutAccountFile


class AccountTx:
    TRANSACTION_DATE = "transaction_date"
    OPERATION_TYPE = "operation_type"
    TITLE = "title"
    COUNTERPARTY = "counterparty"
    ACCOUNT_NUMBER = "account_number"
    AMOUNT = "amount"
    BALANCE = "balance"
    ACCOUNT_ID = "account_id"
    POOL_ID = "pool_id"
    YEAR = "ROK"
    MONTH = "MIESIAC"
    DAY = "DZIEN"
    CAT = "category"

    COLUMN_ORDER = (
        TRANSACTION_DATE,
        OPERATION_TYPE,
        TITLE,
        COUNTERPARTY,
        ACCOUNT_NUMBER,
        AMOUNT,
        BALANCE,
        ACCOUNT_ID,
        POOL_ID,
    )


def empty_account_tx() -> pd.DataFrame:
    return pd.DataFrame(columns=list(AccountTx.COLUMN_ORDER))


def _date_column_for_ymd(df: pd.DataFrame) -> str | None:
    if AccountTx.TRANSACTION_DATE in df.columns:
        return AccountTx.TRANSACTION_DATE
    # Legacy unallocated / stare testy na kolumnach mBank.
    if MBankFile.MBANK_TRANSACTION_DATE in df.columns:
        return MBankFile.MBANK_TRANSACTION_DATE
    return None


def add_ymd_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    date_col = _date_column_for_ymd(df)
    if date_col is None:
        return df

    legacy = [c for c in ("MIESIĄC", "DZIEŃ") if c in df.columns]
    if legacy:
        df = df.drop(columns=legacy)

    if (
        AccountTx.YEAR in df.columns
        and AccountTx.MONTH in df.columns
        and AccountTx.DAY in df.columns
    ):
        if df[AccountTx.YEAR].dtype == object or str(df[AccountTx.YEAR].dtype) == "string":
            return df

    x = pd.to_datetime(df[date_col], errors="coerce")
    df[AccountTx.YEAR] = x.dt.year.astype("string")
    df[AccountTx.MONTH] = x.dt.month.astype("string")
    df[AccountTx.DAY] = x.dt.day.astype("string")
    return df


def mbank_statement_to_account_tx(
    df: pd.DataFrame,
    *,
    account_id: str,
    pool_id: str,
) -> pd.DataFrame:
    if df is None or df.empty:
        return empty_account_tx()

    result = pd.DataFrame(
        {
            AccountTx.TRANSACTION_DATE: pd.to_datetime(
                df[MBankFile.MBANK_TRANSACTION_DATE], errors="coerce"
            ),
            AccountTx.OPERATION_TYPE: df[MBankFile.MBANK_DESCRIPTION].astype("string").fillna(""),
            AccountTx.TITLE: df[MBankFile.MBANK_TITLE].astype("string").fillna(""),
            AccountTx.COUNTERPARTY: df[MBankFile.MBANK_TRANSACTION_PARTY]
            .astype("string")
            .fillna(""),
            AccountTx.ACCOUNT_NUMBER: df[MBankFile.MBANK_ACCOUNT_NUMBER]
            .astype("string")
            .fillna("")
            .str.replace(r"\.0$", "", regex=True),
            AccountTx.AMOUNT: pd.to_numeric(df[MBankFile.MBANK_AMOUNT], errors="coerce"),
            AccountTx.BALANCE: pd.to_numeric(
                df[MBankFile.MBANK_OUTSTANDING_BALANCE], errors="coerce"
            )
            if MBankFile.MBANK_OUTSTANDING_BALANCE in df.columns
            else pd.NA,
            AccountTx.ACCOUNT_ID: account_id,
            AccountTx.POOL_ID: pool_id,
        }
    )
    return result.dropna(subset=[AccountTx.TRANSACTION_DATE, AccountTx.AMOUNT]).reset_index(
        drop=True
    )


def revolut_statement_to_account_tx(
    df: pd.DataFrame,
    *,
    account_id: str,
    pool_id: str,
) -> pd.DataFrame:
    if df is None or df.empty:
        return empty_account_tx()

    result = pd.DataFrame(
        {
            AccountTx.TRANSACTION_DATE: pd.to_datetime(df[RevolutAccountFile.DATE], errors="coerce"),
            AccountTx.OPERATION_TYPE: df[RevolutAccountFile.KIND].astype("string").fillna(""),
            AccountTx.TITLE: df[RevolutAccountFile.DESCRIPTION].astype("string").fillna(""),
            AccountTx.COUNTERPARTY: df[RevolutAccountFile.PRODUCT].astype("string").fillna("")
            if RevolutAccountFile.PRODUCT in df.columns
            else "",
            AccountTx.ACCOUNT_NUMBER: "",
            AccountTx.AMOUNT: pd.to_numeric(df[RevolutAccountFile.AMOUNT], errors="coerce"),
            AccountTx.BALANCE: pd.to_numeric(df[RevolutAccountFile.BALANCE], errors="coerce")
            if RevolutAccountFile.BALANCE in df.columns
            else pd.NA,
            AccountTx.ACCOUNT_ID: account_id,
            AccountTx.POOL_ID: pool_id,
        }
    )
    return result.dropna(subset=[AccountTx.TRANSACTION_DATE, AccountTx.AMOUNT]).reset_index(
        drop=True
    )
