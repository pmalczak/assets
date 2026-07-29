# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from datetime import date

import pandas as pd

from evaluators.valuation_date import filter_excel_rows_on_or_before, format_date_columns
from importers.assets.data_model import AssetsDef, Properties, PropertyValuations
from importers.assets.property_lifecycle import (
    cash_owned_asset_ids,
    latest_valuation_on_date,
    load_property_close_dates,
    property_ids_in_scope,
    valuation_rows_on_date,
)
from importers.assets.read_assets import get_assets_file, read_assets, read_property_valuations
from roi.config import read_analyse_config


def evaluate_assets_file(rodzaj_importu, assets_file_row, valuation_date: date):
    if rodzaj_importu == "assets.properties":
        import warnings

        warnings.warn(
            "assets.properties jest przestarzale; ustaw RODZAJ*=assets.properties-wyceny w assets_1.xlsx",
            DeprecationWarning,
            stacklevel=2,
        )

    f = get_assets_file()

    if rodzaj_importu.startswith('assets.IKE-'):
        df = _read_content(f, assets_file_row)
        df = filter_excel_rows_on_or_before(df, 'Data', valuation_date)
        if df.empty:
            return None
        df['Data'] = df['Data'].dt.strftime('%Y-%m-%d')
        last = df[-1:]
        for _, row in last.iterrows():
            assets_row = AssetsDef.as_assets_row(assets_file_row)
            assets_row[AssetsDef.EVALUATION_DATE] = row['Data']
            assets_row[AssetsDef.VALUE] = row['wartość']
            break
        data = [assets_row]

        result = pd.DataFrame(data=data)
        AssetsDef.check_structure(result)
        return format_date_columns(result, AssetsDef.EVALUATION_DATE)

    if rodzaj_importu in ('assets.properties-wyceny', 'assets.properties'):
        return _evaluate_property_valuations(assets_file_row, valuation_date)

    elif rodzaj_importu == 'assets.cash':
        return _evaluate_single_property_id(assets_file_row, valuation_date)

    else:
        raise ValueError(f'brakujący typ: {rodzaj_importu}')


def _evaluate_single_property_id(
    assets_file_row: pd.Series,
    valuation_date: date,
) -> pd.DataFrame | None:
    """Jedno id z asset-evaluation (np. cash, rocky-iv) — bez rozwijania całego arkusza."""
    valuations = read_property_valuations()
    PropertyValuations.check_structure(valuations)
    config = read_analyse_config()
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
    close_dates = load_property_close_dates(config["manual"], config["catalog"])

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


def _read_content(f, assets_file_row: pd.Series = None):
    kind: str = assets_file_row[AssetsDef.KIND]
    sheet = kind.split('.')[1]

    df = pd.read_excel(f, sheet_name=sheet)
    return df
