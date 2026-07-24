# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date

import pandas as pd

from analyse_assets.config_model import AnalyseAssetsManual
from evaluators.valuation_date import filter_excel_rows_on_or_before
from importers.assets.data_model import OperationDomain, Properties

CLOSING_CATEGORY = "CLOSING"


def load_property_close_dates(
    manual: pd.DataFrame,
    _catalog: pd.DataFrame | None = None,
) -> dict[str, date]:
    """Daty zamkniecia z ROI manual (CLOSING), indeksowane po asset_id."""
    if manual.empty:
        return {}

    closing = manual[manual[AnalyseAssetsManual.CATEGORY] == CLOSING_CATEGORY].copy()
    if closing.empty:
        return {}

    closing[AnalyseAssetsManual.DATE] = pd.to_datetime(
        closing[AnalyseAssetsManual.DATE],
        errors="coerce",
    )
    closing = closing.dropna(subset=[AnalyseAssetsManual.DATE])
    by_asset_id: dict[str, date] = {}
    for asset_id, group in closing.groupby(AnalyseAssetsManual.ASSET_ID):
        earliest = group[AnalyseAssetsManual.DATE].min()
        by_asset_id[str(asset_id)] = earliest.date()
    return by_asset_id


def property_ids_in_scope(
    valuations: pd.DataFrame,
    close_dates: dict[str, date],
) -> set[str]:
    """Id nieruchomosci z wycen lub z datami zamkniecia w ROI."""
    ids: set[str] = set()
    if not valuations.empty:
        ids |= set(valuations[Properties.ID].astype(str).unique())
    ids |= {str(key) for key in close_dates}
    return ids


def is_property_closed(
    properties_id: str,
    valuation_date: date,
    close_dates: dict[str, date],
) -> bool:
    close_date = close_dates.get(str(properties_id))
    if close_date is None:
        return False
    return valuation_date >= close_date


def valuation_rows_on_date(
    valuations: pd.DataFrame,
    properties_id: str,
    valuation_date: date,
    close_dates: dict[str, date],
) -> pd.DataFrame:
    if valuations.empty or is_property_closed(properties_id, valuation_date, close_dates):
        return pd.DataFrame(columns=valuations.columns)

    asset_rows = valuations[valuations[Properties.ID].astype(str) == str(properties_id)].copy()
    if asset_rows.empty:
        return asset_rows

    asset_rows = filter_excel_rows_on_or_before(asset_rows, Properties.DATE, valuation_date)
    allowed_ops = {OperationDomain.BUY, OperationDomain.EVALUATION}
    return asset_rows[asset_rows[Properties.OPERATION].isin(allowed_ops)]


def latest_valuation_on_date(
    valuations: pd.DataFrame,
    properties_id: str,
    valuation_date: date,
    close_dates: dict[str, date],
) -> tuple[float, date] | None:
    rows = valuation_rows_on_date(valuations, properties_id, valuation_date, close_dates)
    if rows.empty:
        return None

    latest = rows.sort_values(Properties.DATE, ascending=False).iloc[0]
    value = float(latest[Properties.VALUE])
    evaluation_date = pd.Timestamp(latest[Properties.DATE]).date()
    return value, evaluation_date


def property_valuation_history(
    valuations: pd.DataFrame,
    properties_id: str,
    close_dates: dict[str, date],
) -> pd.DataFrame:
    """Punkty historii wartosci + zero w dniu zamkniecia (jesli znane)."""
    if valuations.empty:
        return pd.DataFrame(columns=["date", "value", "currency"])

    asset_rows = valuations[valuations[Properties.ID].astype(str) == str(properties_id)].copy()
    if asset_rows.empty:
        return pd.DataFrame(columns=["date", "value", "currency"])

    allowed_ops = {OperationDomain.BUY, OperationDomain.EVALUATION}
    history = asset_rows[asset_rows[Properties.OPERATION].isin(allowed_ops)].copy()
    history[Properties.DATE] = pd.to_datetime(history[Properties.DATE], errors="coerce")
    history[Properties.VALUE] = pd.to_numeric(history[Properties.VALUE], errors="coerce")
    history = history.dropna(subset=[Properties.DATE, Properties.VALUE])
    if history.empty:
        return pd.DataFrame(columns=["date", "value", "currency"])

    history = history.rename(
        columns={
            Properties.DATE: "date",
            Properties.VALUE: "value",
            Properties.CURRENCY: "currency",
        }
    )
    history = history.groupby("date", as_index=False).last()

    close_date = close_dates.get(str(properties_id))
    if close_date is not None:
        close_ts = pd.Timestamp(close_date)
        history = history[history["date"] <= close_ts]
        zero_row = pd.DataFrame(
            [{"date": close_ts, "value": 0.0, "currency": history["currency"].iloc[-1]}]
        )
        history = pd.concat([history, zero_row], ignore_index=True)
        history = history.groupby("date", as_index=False).last()

    return history[["date", "value", "currency"]]
