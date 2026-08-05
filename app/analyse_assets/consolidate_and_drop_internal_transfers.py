# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from typing import List

import numpy as np
import pandas as pd

from analyse_assets.account_tx import AccountTx, add_ymd_columns
from importers.mbank.data_model import MbankOperationType

_MBANK_PHRASE_IN = MbankOperationType.PRZELEW_WEWNETRZNY_PRZYCHODZACY
_MBANK_PHRASES_OUT = [
    MbankOperationType.PRZELEW_WEWNETRZNY_WYCHODZACY,
    MbankOperationType.PRZELEW_WLASNY,
]

_REVOLUT_TRANSFER_PHRASES = (
    "transfer",
    "exchange",
    "wymiana",
    "przelew",
)


def _contains_ci(text: str, phrase: str) -> bool:
    if pd.isna(text):
        return False
    return re.search(re.escape(phrase), str(text), flags=re.IGNORECASE) is not None


def _contains_any_ci(text: str, phrases: list[str] | tuple[str, ...]) -> bool:
    return any(_contains_ci(text, p) for p in phrases)


def consolidate_account_tx_drop_internal_transfers(
    statements: List[pd.DataFrame],
    *,
    bank: str = "mbank",
    date_tolerance: str = "D",
    require_opposite_sign: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Konsoliduje AccountTx i usuwa sparowane przelewy wewnętrzne."""
    if not statements:
        empty = pd.DataFrame(columns=list(AccountTx.COLUMN_ORDER))
        return empty, pd.DataFrame(), {"input_rows": 0, "pairs_removed": 0, "output_rows": 0}

    df = pd.concat(statements, ignore_index=True)
    if df.empty:
        return df, pd.DataFrame(), {"input_rows": 0, "pairs_removed": 0, "output_rows": 0}

    col_date = AccountTx.TRANSACTION_DATE
    col_amount = AccountTx.AMOUNT
    col_account_id = AccountTx.ACCOUNT_ID
    col_counterparty_account = AccountTx.ACCOUNT_NUMBER
    col_title = AccountTx.TITLE
    col_op = AccountTx.OPERATION_TYPE

    df[col_date] = pd.to_datetime(df[col_date], errors="coerce")
    df["_sign"] = np.where(df[col_amount] >= 0, 1, -1)
    df["_amount_abs"] = df[col_amount].abs()
    df["_bucket_time"] = df[col_date].dt.floor(date_tolerance)

    if bank.startswith("mbank"):
        df["_internal_in"] = df[col_op].map(lambda x: _contains_ci(x, _MBANK_PHRASE_IN))
        df["_internal_out"] = df[col_op].map(lambda x: _contains_any_ci(x, _MBANK_PHRASES_OUT))
        df["_internal_type"] = np.select(
            [df["_internal_in"], df["_internal_out"]],
            ["IN", "OUT"],
            default="",
        )
        internal = df[df["_internal_type"].isin(["IN", "OUT"])].copy()
        external = df[~df.index.isin(internal.index)].copy()
        if not internal.empty:
            mask_self = internal[col_account_id].astype(str) != internal[
                col_counterparty_account
            ].astype(str)
            internal = internal[mask_self].copy()
            a = internal[col_account_id].astype(str).to_numpy()
            b = internal[col_counterparty_account].astype(str).to_numpy()
            internal["_acc_min"] = np.where(a < b, a, b)
            internal["_acc_max"] = np.where(a < b, b, a)
            tkey = (
                internal[col_title]
                .fillna("")
                .astype(str)
                .str.lower()
                .str.replace(r"\s+", " ", regex=True)
                .str[:40]
            )
            internal["_pair_bucket"] = (
                internal["_acc_min"].astype(str)
                + "||"
                + internal["_acc_max"].astype(str)
                + "||"
                + internal["_bucket_time"].astype(str)
                + "||"
                + internal["_amount_abs"].astype(str)
                + "||"
                + tkey.astype(str)
            )
    else:
        # Revolut: sparuj przeciwne znaki / ta sama kwota / ten sam dzień między różnymi kontami.
        transfer_mask = df[col_op].map(lambda x: _contains_any_ci(x, _REVOLUT_TRANSFER_PHRASES))
        candidates = df[transfer_mask].copy()
        external = df[~transfer_mask].copy()
        if not candidates.empty:
            candidates["_pair_bucket"] = (
                candidates["_bucket_time"].astype(str)
                + "||"
                + candidates["_amount_abs"].astype(str)
            )
            candidates["_internal_type"] = np.where(candidates["_sign"] >= 0, "IN", "OUT")
        internal = candidates

    if internal.empty:
        cleaned = external.copy()
        cleaned = cleaned.drop(
            columns=[
                "_sign",
                "_amount_abs",
                "_bucket_time",
                "_internal_in",
                "_internal_out",
                "_internal_type",
            ],
            errors="ignore",
        ).sort_values(by=[col_date]).reset_index(drop=True)
        cleaned = add_ymd_columns(cleaned)
        meta = {
            "input_rows": sum(len(x) for x in statements),
            "pairs_removed": 0,
            "rows_removed": 0,
            "output_rows": len(cleaned),
            "bank": bank,
        }
        return cleaned, pd.DataFrame(), meta

    internal["_row_id"] = internal.index
    df_in = internal[internal["_internal_type"] == "IN"].copy()
    df_out = internal[internal["_internal_type"] == "OUT"].copy()

    # Bez obu stron nie ma pary — merge na pustej stronie bez _rank kończył się KeyError.
    if df_in.empty or df_out.empty:
        pairs = pd.DataFrame()
        to_drop: set = set()
    else:
        df_in["_rank"] = df_in.groupby("_pair_bucket").cumcount()
        df_out["_rank"] = df_out.groupby("_pair_bucket").cumcount()
        pairs = pd.merge(
            df_in,
            df_out,
            on=["_pair_bucket", "_rank"],
            suffixes=("_in", "_out"),
            how="inner",
        )
        if require_opposite_sign and not pairs.empty:
            pairs = pairs[pairs["_sign_in"] != pairs["_sign_out"]]
        if bank.startswith("revolut") and not pairs.empty:
            pairs = pairs[
                pairs[f"{col_account_id}_in"].astype(str)
                != pairs[f"{col_account_id}_out"].astype(str)
            ]
        to_drop = set()
        if not pairs.empty:
            to_drop = set(pairs["_row_id_in"].tolist()) | set(pairs["_row_id_out"].tolist())

    cleaned_internal = internal.drop(index=list(to_drop), errors="ignore")
    cleaned = pd.concat([external, cleaned_internal], ignore_index=False)
    cleaned = cleaned.drop(
        columns=[
            "_sign",
            "_amount_abs",
            "_bucket_time",
            "_acc_min",
            "_acc_max",
            "_internal_in",
            "_internal_out",
            "_internal_type",
            "_pair_bucket",
            "_row_id",
            "_rank",
        ],
        errors="ignore",
    ).sort_values(by=[col_date]).reset_index(drop=True)
    cleaned = add_ymd_columns(cleaned)

    report = pairs if isinstance(pairs, pd.DataFrame) else pd.DataFrame()
    meta = {
        "input_rows": sum(len(x) for x in statements),
        "pairs_removed": len(pairs) if isinstance(pairs, pd.DataFrame) else 0,
        "rows_removed": len(to_drop),
        "output_rows": len(cleaned),
        "bank": bank,
    }
    return cleaned, report, meta
