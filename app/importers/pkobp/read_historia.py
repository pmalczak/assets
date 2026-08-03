# -*- coding: utf-8 -*-
"""Historia dyspozycji PKO BP — inventory (qty) + ledger pod ROI."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from data_step.data_step import DATA_STEP
from importers.pkobp.data_model import (
    MANUAL_CASHFLOW_ROWS,
    PAPER_SELL_TYPES,
    QTY_BUY_TYPES,
    QTY_ORDER_TYPES,
    QTY_SELL_TYPES,
    PkoBpBonds,
    is_cashflow_register,
    normalized_cashflow_amount,
)
from importers.pkobp.historia_dyspozycji import resolve_historia_file


def read_obligacje_historia(input_path: Path, asset_id: str) -> pd.DataFrame:
    resource = f"01 source/{asset_id}-historia.parquet"
    r = DATA_STEP.obtain_dependent(resource, import_historia, input_path)
    return r.data_frame()


def import_historia(source_file: Path = None) -> pd.DataFrame:
    assert source_file is not None and source_file.is_dir()
    input_file = resolve_historia_file(source_file)

    transactions = pd.read_excel(input_file)
    PkoBpBonds.check_structure(transactions)

    print(f"PLIK:{input_file} {len(transactions):>4} rekord/ów")
    transactions = transactions[transactions[PkoBpBonds.STAT] == "zrealizowana"].copy()
    transactions = transactions[transactions[PkoBpBonds.CODE] != "TZ0208"].copy()
    transactions = _negate_paper_sell_qty(transactions)
    transactions = _append_manual_cashflows(transactions)
    transactions = _normalize_cashflow_amounts(transactions)
    return transactions.reset_index(drop=True)


def _negate_paper_sell_qty(df: pd.DataFrame) -> pd.DataFrame:
    """Przy imporcie: LICZBA OBLIGACJI *= -1 dla wykupu / przedterminowego wykupu (papiery)."""
    out = df.copy()
    sell = out[PkoBpBonds.ORDER_TYPE].isin(PAPER_SELL_TYPES)
    qty = pd.to_numeric(out.loc[sell, PkoBpBonds.BONDS_NO], errors="coerce").fillna(0)
    out.loc[sell, PkoBpBonds.BONDS_NO] = -qty.abs()
    return out


def _normalize_cashflow_amounts(df: pd.DataFrame) -> pd.DataFrame:
    """
    Przy imporcie do 01 source: znaki KWOTA wg kierunku wartości instrumentu
    (CAPEX/REVENUES ujemne, OPEX/DIVESTMENT dodatnie).
    """
    out = df.copy()
    mask = out[PkoBpBonds.ORDER_TYPE].map(is_cashflow_register)
    if not mask.any():
        return out
    amounts = pd.to_numeric(out.loc[mask, PkoBpBonds.AMOUNT], errors="coerce")
    types = out.loc[mask, PkoBpBonds.ORDER_TYPE]
    out.loc[mask, PkoBpBonds.AMOUNT] = [
        normalized_cashflow_amount(t, a) if pd.notna(a) else a
        for t, a in zip(types, amounts, strict=True)
    ]
    return out


def _append_manual_cashflows(df: pd.DataFrame) -> pd.DataFrame:
    manual = pd.DataFrame(list(MANUAL_CASHFLOW_ROWS))
    if manual.empty:
        return df
    # Nie duplikuj, jeśli ten sam zestaw data/typ/kod/kwota już jest.
    keys = [PkoBpBonds.DATE, PkoBpBonds.ORDER_TYPE, PkoBpBonds.CODE, PkoBpBonds.AMOUNT]
    existing = df.copy()
    existing["_k"] = (
        existing[PkoBpBonds.DATE].astype(str)
        + "|"
        + existing[PkoBpBonds.ORDER_TYPE].astype(str)
        + "|"
        + existing[PkoBpBonds.CODE].astype(str)
        + "|"
        + pd.to_numeric(existing[PkoBpBonds.AMOUNT], errors="coerce").round(2).astype(str)
    )
    manual["_k"] = (
        manual[PkoBpBonds.DATE].astype(str)
        + "|"
        + manual[PkoBpBonds.ORDER_TYPE].astype(str)
        + "|"
        + manual[PkoBpBonds.CODE].astype(str)
        + "|"
        + pd.to_numeric(manual[PkoBpBonds.AMOUNT], errors="coerce").round(2).astype(str)
    )
    to_add = manual.loc[~manual["_k"].isin(set(existing["_k"]))].drop(columns=["_k"])
    if to_add.empty:
        return df
    print(f"MANUAL cashflows: +{len(to_add)} wiersz/y")
    return pd.concat([df, to_add], ignore_index=True)


def filter_historia_on_or_before(df: pd.DataFrame, valuation_date: date) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=list(PkoBpBonds.expected_columns()))
    work = df.copy()
    work["_dt"] = pd.to_datetime(work[PkoBpBonds.DATE], errors="coerce")
    cutoff = pd.Timestamp(valuation_date)
    work = work.loc[work["_dt"].notna() & (work["_dt"] <= cutoff)]
    return work.drop(columns=["_dt"]).reset_index(drop=True)


def qty_signed_ops(historia: pd.DataFrame) -> pd.DataFrame:
    """Operacje na papierach; LICZBA już ze znakiem po imporcie (sell ujemne)."""
    if historia is None or historia.empty:
        return pd.DataFrame(
            columns=[PkoBpBonds.DATE, PkoBpBonds.CODE, PkoBpBonds.ORDER_TYPE, PkoBpBonds.BONDS_NO]
        )
    mask = historia[PkoBpBonds.ORDER_TYPE].isin(QTY_ORDER_TYPES)
    ops = historia.loc[mask, [PkoBpBonds.DATE, PkoBpBonds.CODE, PkoBpBonds.ORDER_TYPE, PkoBpBonds.BONDS_NO]].copy()
    ops[PkoBpBonds.BONDS_NO] = pd.to_numeric(ops[PkoBpBonds.BONDS_NO], errors="coerce").fillna(0)
    # Idempotentnie: buy ≥0, sell ≤0 (nawet gdy import jeszcze nie podpisał).
    sell = ops[PkoBpBonds.ORDER_TYPE].isin(QTY_SELL_TYPES)
    buy = ops[PkoBpBonds.ORDER_TYPE].isin(QTY_BUY_TYPES)
    ops.loc[sell, PkoBpBonds.BONDS_NO] = -ops.loc[sell, PkoBpBonds.BONDS_NO].abs()
    ops.loc[buy, PkoBpBonds.BONDS_NO] = ops.loc[buy, PkoBpBonds.BONDS_NO].abs()
    return ops.reset_index(drop=True)


def open_qty_by_code(historia: pd.DataFrame, valuation_date: date | None = None) -> dict[str, float]:
    work = historia
    if valuation_date is not None:
        work = filter_historia_on_or_before(work, valuation_date)
    ops = qty_signed_ops(work)
    if ops.empty:
        return {}
    grouped = ops.groupby(PkoBpBonds.CODE, as_index=True)[PkoBpBonds.BONDS_NO].sum()
    return {str(code): float(qty) for code, qty in grouped.items()}


def filter_cashflow_register(historia: pd.DataFrame) -> pd.DataFrame:
    """Rejestr przepływy pieniężne (status już odfiltrowany w import_historia)."""
    if historia is None or historia.empty:
        return pd.DataFrame(columns=list(PkoBpBonds.expected_columns()))
    mask = historia[PkoBpBonds.ORDER_TYPE].map(is_cashflow_register)
    return historia.loc[mask].reset_index(drop=True)
