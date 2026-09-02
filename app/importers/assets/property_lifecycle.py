# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date

import pandas as pd

from analyse_assets.config_model import AnalyseAssetsManual
from evaluators.valuation_date import filter_excel_rows_on_or_before
from importers.assets.data_model import AssetsFile, OperationDomain, Properties

CASH_KIND = "assets.cash"


def cash_owned_asset_ids(assets_catalog: pd.DataFrame) -> set[str]:
    """Id z katalogu assets o RODZAJ*=assets.cash (np. cash, rocky-iv)."""
    if assets_catalog is None or assets_catalog.empty:
        return set()
    if AssetsFile.KIND not in assets_catalog.columns or AssetsFile.ID not in assets_catalog.columns:
        return set()
    mask = assets_catalog[AssetsFile.KIND].astype(str) == CASH_KIND
    return set(assets_catalog.loc[mask, AssetsFile.ID].astype(str))


def investment_property_ids(assets_catalog: pd.DataFrame | None = None) -> set[str]:
    """Id z katalogu assets o typ=investment.property."""
    from importers.assets.data_model import TypeDomain
    from importers.assets.read_assets import read_assets

    if assets_catalog is None:
        assets_catalog = read_assets()
    if assets_catalog is None or assets_catalog.empty:
        return set()
    if AssetsFile.TYPE not in assets_catalog.columns or AssetsFile.ID not in assets_catalog.columns:
        return set()
    mask = assets_catalog[AssetsFile.TYPE].astype(str) == TypeDomain.PROPERTY
    return set(assets_catalog.loc[mask, AssetsFile.ID].astype(str))


def earliest_divestment_dates(events: pd.DataFrame) -> dict[str, date]:
    """Najwcześniejsza data DIVESTMENT per asset_id z cashflowów ROI."""
    from roi.categories import DIVESTMENT, normalize_roi_category
    from roi.data_model import CashFlowEvent

    if events is None or events.empty:
        return {}
    if CashFlowEvent.CATEGORY not in events.columns or CashFlowEvent.DATE not in events.columns:
        return {}

    mask = events[CashFlowEvent.CATEGORY].astype(str).map(normalize_roi_category) == DIVESTMENT
    closing = events.loc[mask].copy()
    if closing.empty:
        return {}

    closing[CashFlowEvent.DATE] = pd.to_datetime(closing[CashFlowEvent.DATE], errors="coerce")
    closing = closing.dropna(subset=[CashFlowEvent.DATE])
    by_asset_id: dict[str, date] = {}
    for asset_id, group in closing.groupby(CashFlowEvent.ASSET_ID):
        by_asset_id[str(asset_id)] = group[CashFlowEvent.DATE].min().date()
    return by_asset_id


def load_property_close_dates(
    manual: pd.DataFrame,
    _catalog: pd.DataFrame | None = None,
    events: pd.DataFrame | None = None,
) -> dict[str, date]:
    """Daty zamkniecia: manual DIVESTMENT (+ dla investment.property także DIVESTMENT z CF)."""
    from roi.categories import DIVESTMENT, normalize_roi_category

    by_asset_id: dict[str, date] = {}

    if manual is not None and not manual.empty:
        cats = manual[AnalyseAssetsManual.CATEGORY].astype(str).map(normalize_roi_category)
        closing = manual[cats == DIVESTMENT].copy()
        if not closing.empty:
            closing[AnalyseAssetsManual.DATE] = pd.to_datetime(
                closing[AnalyseAssetsManual.DATE],
                errors="coerce",
            )
            closing = closing.dropna(subset=[AnalyseAssetsManual.DATE])
            for asset_id, group in closing.groupby(AnalyseAssetsManual.ASSET_ID):
                by_asset_id[str(asset_id)] = group[AnalyseAssetsManual.DATE].min().date()

    # Nieruchomość: DIVESTMENT (bank lub manual w events) = zamknięcie pozycji.
    # ID z roi_def (np. horbaczewskiego) nie musi być wierszem assets (tam rodzic `properties`).
    if events is not None and not events.empty:
        for asset_id, close_date in earliest_divestment_dates(events).items():
            previous = by_asset_id.get(asset_id)
            by_asset_id[asset_id] = (
                close_date if previous is None else min(previous, close_date)
            )

    return by_asset_id


def property_ids_in_scope(
    valuations: pd.DataFrame,
    close_dates: dict[str, date],
    exclude_ids: set[str] | None = None,
) -> set[str]:
    """Id nieruchomosci z wycen lub z datami zamkniecia w ROI.

    ``exclude_ids`` — np. id z wierszy ``assets.cash`` (cash, rocky-iv), ktore
    maja wlasna sciezke ewaluacji i nie powinny byc rozwijane przez properties.
    """
    ids: set[str] = set()
    if not valuations.empty:
        ids |= set(valuations[Properties.ID].astype(str).unique())
    ids |= {str(key) for key in close_dates}
    if exclude_ids:
        ids -= {str(asset_id) for asset_id in exclude_ids}
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
