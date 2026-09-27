# -*- coding: utf-8 -*-
"""Arkusze IKE w a_config.xlsx: inventory (IKE-PM / IKE-GM) + kurs (IKE-kurs)."""
from __future__ import annotations

from datetime import date
from typing import Literal

import pandas as pd

from evaluators.valuation_date import filter_excel_rows_on_or_before
from importers.assets.read_assets import get_assets_file, read_asset_sheet
from importers.data_model_generic import GenericStructureClass

IkeAccount = Literal["pm", "gm"]

IKE_PM_SHEET = "IKE-PM"
IKE_GM_SHEET = "IKE-GM"
IKE_KURS_SHEET = "IKE-kurs"

IKE_ACCOUNT_SHEET: dict[str, str] = {
    "pm": IKE_PM_SHEET,
    "gm": IKE_GM_SHEET,
}

IKE_ACCOUNT_ASSET_ID: dict[str, str] = {
    "pm": "pm_ike",
    "gm": "gm_ike",
}

IKE_KIND_TO_ACCOUNT: dict[str, str] = {
    "assets.IKE-PM": "pm",
    "assets.IKE-GM": "gm",
}


class IkeInventoryCls(GenericStructureClass):
    PRODUCT = "Produkt"
    DATE = "Data"
    UNITS = "Liczba jednostek"
    VALUE = "wartość"
    CURRENCY = "waluta"

    def expected_columns(self) -> set:
        return {self.PRODUCT, self.DATE, self.UNITS, self.VALUE, self.CURRENCY}


class IkeKursCls(GenericStructureClass):
    PRODUCT = "Produkt"
    DATE = "Data"
    PRICE = "kurs"

    def expected_columns(self) -> set:
        return {self.PRODUCT, self.DATE, self.PRICE}


IkeInventory = IkeInventoryCls()
IkeKurs = IkeKursCls()


def sheet_for_account(account: IkeAccount | str) -> str:
    key = str(account).strip().lower()
    if key not in IKE_ACCOUNT_SHEET:
        raise ValueError(f"Nieznane konto IKE: {account!r} (oczekiwane: pm|gm)")
    return IKE_ACCOUNT_SHEET[key]


def asset_id_for_account(account: IkeAccount | str) -> str:
    key = str(account).strip().lower()
    if key not in IKE_ACCOUNT_ASSET_ID:
        raise ValueError(f"Nieznane konto IKE: {account!r} (oczekiwane: pm|gm)")
    return IKE_ACCOUNT_ASSET_ID[key]


def account_for_kind(rodzaj: str) -> str | None:
    return IKE_KIND_TO_ACCOUNT.get(str(rodzaj).strip())


def read_ike_inventory(account: IkeAccount | str) -> pd.DataFrame:
    """Inventory zakupów/umorzeń z arkusza IKE-PM lub IKE-GM."""
    source = get_assets_file()
    assert source.is_file(), source
    sheet = sheet_for_account(account)
    df = read_asset_sheet(sheet)
    if df is None or df.empty:
        return pd.DataFrame(columns=list(IkeInventory.expected_columns()))
    IkeInventory.check_structure(df, file=source)
    return df.copy()


def read_ike_kurs() -> pd.DataFrame:
    """Historia kursu jednostki z arkusza IKE-kurs."""
    source = get_assets_file()
    assert source.is_file(), source
    df = read_asset_sheet(IKE_KURS_SHEET)
    if df is None or df.empty:
        return pd.DataFrame(columns=list(IkeKurs.expected_columns()))
    IkeKurs.check_structure(df, file=source)
    return df.copy()


def ike_terminal_value(
    inventory: pd.DataFrame,
    kurs: pd.DataFrame,
    as_of: date,
    *,
    product: str | None = None,
) -> tuple[float, date] | None:
    """NAV per Produkt: Σ jednostek × ostatni kurs ≤ as_of; suma po produktach.

    ``data wyceny`` = najpóźniejsza data kursu użyta wśród produktów z qty≠0.
    Brak kursu przy qty>0 dla produktu → ValueError.
    """
    inv = filter_excel_rows_on_or_before(inventory, IkeInventory.DATE, as_of)
    if inv.empty:
        return None
    if product is not None:
        inv = inv[inv[IkeInventory.PRODUCT].astype(str) == str(product)]
    if inv.empty:
        return None

    if kurs is None or kurs.empty or IkeKurs.PRODUCT not in getattr(kurs, "columns", []):
        raise ValueError(f"IKE: brak arkusza/wierszy kursu na {as_of.isoformat()}")

    prices_all = filter_excel_rows_on_or_before(kurs, IkeKurs.DATE, as_of)
    if prices_all.empty:
        raise ValueError(f"IKE: brak kursów ≤ {as_of.isoformat()}")

    inv = inv.copy()
    inv[IkeInventory.PRODUCT] = inv[IkeInventory.PRODUCT].astype(str)
    inv["_units"] = pd.to_numeric(inv[IkeInventory.UNITS], errors="coerce").fillna(0.0)

    total = 0.0
    eval_dates: list[date] = []
    for prod, group in inv.groupby(IkeInventory.PRODUCT, sort=True):
        qty = float(group["_units"].sum())
        if abs(qty) < 1e-12:
            continue
        prices = prices_all[prices_all[IkeKurs.PRODUCT].astype(str) == str(prod)]
        if prices.empty:
            raise ValueError(
                f"IKE: brak kursu dla {prod!r} na {as_of.isoformat()} (qty={qty})"
            )
        last = prices.sort_values(IkeKurs.DATE).iloc[-1]
        price = float(last[IkeKurs.PRICE])
        eval_ts = pd.Timestamp(last[IkeKurs.DATE])
        if pd.isna(eval_ts):
            raise ValueError(f"IKE: nieparsowalna data kursu dla {prod!r}")
        total += qty * price
        eval_dates.append(eval_ts.date())

    if not eval_dates:
        return None
    return total, max(eval_dates)
