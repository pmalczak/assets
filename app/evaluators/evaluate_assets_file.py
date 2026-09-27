# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from datetime import date

import pandas as pd

from evaluators.valuation_date import format_date_columns
from importers.assets.data_model import AssetsDef, Properties, PropertyValuations
from importers.assets.ike import (
    account_for_kind,
    ike_terminal_value,
    read_ike_inventory,
    read_ike_kurs,
)
from importers.assets.property_lifecycle import (
    cash_owned_asset_ids,
    latest_valuation_on_date,
    load_property_close_dates,
    property_ids_in_scope,
    valuation_rows_on_date,
)
from importers.assets.read_assets import read_assets, read_property_valuations
from roi.config import read_analyse_config
from roi.terminal_value import load_roi_aware_close_dates


def evaluate_assets_file(rodzaj_importu, assets_file_row, valuation_date: date):
    if rodzaj_importu == "assets.properties":
        import warnings

        warnings.warn(
            "assets.properties jest przestarzale; ustaw RODZAJ*=assets.properties-wyceny w a_config.xlsx",
            DeprecationWarning,
            stacklevel=2,
        )

    if rodzaj_importu.startswith("assets.IKE-"):
        return _evaluate_ike(assets_file_row, valuation_date, rodzaj_importu)

    if rodzaj_importu in ('assets.properties-wyceny', 'assets.properties'):
        return _evaluate_property_valuations(assets_file_row, valuation_date)

    elif rodzaj_importu == 'assets.cash':
        return _evaluate_single_property_id(assets_file_row, valuation_date)

    else:
        raise ValueError(f'brakujący typ: {rodzaj_importu}')


def _evaluate_ike(
    assets_file_row: pd.Series,
    valuation_date: date,
    rodzaj_importu: str,
) -> pd.DataFrame | None:
    """NAV IKE = Σ_Produkt (Σ jednostek × ostatni kurs); data wyceny = data kursu."""
    account = account_for_kind(rodzaj_importu)
    if account is None:
        raise ValueError(f"Nieznany RODZAJ* IKE: {rodzaj_importu!r}")

    inventory = read_ike_inventory(account)
    kurs = read_ike_kurs()
    terminal = ike_terminal_value(inventory, kurs, valuation_date)
    if terminal is None:
        return None

    value, evaluation_date = terminal
    assets_row = AssetsDef.as_assets_row(assets_file_row)
    assets_row[AssetsDef.EVALUATION_DATE] = evaluation_date
    assets_row[AssetsDef.VALUE] = value
    assets_row[AssetsDef.CURRENCY] = "PLN"

    result = pd.DataFrame([assets_row])
    AssetsDef.check_structure(result)
    return format_date_columns(result, AssetsDef.EVALUATION_DATE)


def _evaluate_single_property_id(
    assets_file_row: pd.Series,
    valuation_date: date,
) -> pd.DataFrame | None:
    """Jedno id z asset-evaluation (np. cash, rocky-iv) — bez rozwijania całego arkusza."""
    valuations = read_property_valuations()
    PropertyValuations.check_structure(valuations)
    config = read_analyse_config()
    # cash / rocky-iv: zamknięcie wyłącznie z roi_manual (nie z CF property).
    close_dates = load_property_close_dates(config["manual"], config["catalog"])

    properties_id = str(assets_file_row[AssetsDef.ID])
    latest = latest_valuation_on_date(valuations, properties_id, valuation_date, close_dates)
    if latest is None:
        return None

    value, evaluation_date = latest
    assets_row = AssetsDef.as_assets_row(assets_file_row)
    assets_row[AssetsDef.ID] = properties_id
    assets_row[AssetsDef.EVALUATION_DATE] = evaluation_date
    assets_row[AssetsDef.VALUE] = value

    rows = valuation_rows_on_date(valuations, properties_id, valuation_date, close_dates)
    if not rows.empty:
        latest_row = rows.sort_values(Properties.DATE, ascending=False).iloc[0]
        currency = latest_row.get(Properties.CURRENCY)
        if currency is not None and not pd.isna(currency) and str(currency).strip():
            assets_row[AssetsDef.CURRENCY] = str(currency).strip().upper()

    result = pd.DataFrame([assets_row])
    AssetsDef.check_structure(result)
    return format_date_columns(result, AssetsDef.EVALUATION_DATE)


def _evaluate_property_valuations(assets_file_row: pd.Series, valuation_date: date) -> pd.DataFrame | None:
    valuations = read_property_valuations()
    PropertyValuations.check_structure(valuations)
    config = read_analyse_config()
    close_dates = load_roi_aware_close_dates(valuation_date, config)

    property_ids = sorted(
        property_ids_in_scope(
            valuations,
            close_dates,
            exclude_ids=cash_owned_asset_ids(read_assets()),
        )
    )
    result = []
    for properties_id in property_ids:
        latest = latest_valuation_on_date(valuations, properties_id, valuation_date, close_dates)
        if latest is None:
            continue
        value, evaluation_date = latest
        assets_row = AssetsDef.as_assets_row(assets_file_row)
        assets_row[AssetsDef.ID] = properties_id
        assets_row[AssetsDef.EVALUATION_DATE] = evaluation_date
        assets_row[AssetsDef.VALUE] = value
        result.append(assets_row)

    if not result:
        return None

    result = pd.DataFrame(data=result)
    AssetsDef.check_structure(result)
    return format_date_columns(result, AssetsDef.EVALUATION_DATE)
