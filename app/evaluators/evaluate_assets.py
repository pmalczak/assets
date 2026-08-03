# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from datetime import date
from pathlib import Path

import pandas as pd

from fx.data_model import LastFx
from importers.assets.data_model import AssetsDef, KindDomain, TypeDomain
from evaluators.evaluate_assets_file import evaluate_assets_file
from evaluators.evaluate_broker_obligacje import evaluate_broker_obligacje, is_obligacje_broker
from evaluators.evaluate_broker_revolut import evaluate_broker_revolut
from evaluators.evaluate_mbank import evaluate_mbank
from evaluators.evaluate_revolut import evaluate_revolut
from evaluators.evaluate_zloto_monety import evaluate_zloto_monety
from evaluators.valuation_date import format_date_columns
from fx.get_last_fx import get_fx_as_of


def evaluate_assets(
    data_root: Path,
    assets: pd.DataFrame,
    fx_rates: pd.DataFrame,
    valuation_date: date,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Ewaluacja wierszy z assets_1.
    Zwraca (ramka z VALUE_PLN/FX, lista ostrzeżeń).
    """
    result = []
    warnings: list[str] = []
    a = assets[assets[AssetsDef.KIND].notnull()]
    for i, assets_file_row in a.iterrows():
        assert isinstance(assets_file_row, pd.Series)
        rodzaj_importu: str = assets_file_row[AssetsDef.KIND]
        asset_id = str(assets_file_row[AssetsDef.ID])

        if rodzaj_importu.startswith(KindDomain.MBANK):
            r = evaluate_mbank(data_root, asset_id, assets_file_row, valuation_date)
            if not r.empty:
                AssetsDef.check_structure(r)
                result += [r]

        elif rodzaj_importu.startswith(KindDomain.REVOLUT):
            r = evaluate_revolut(data_root, asset_id, assets_file_row, valuation_date)
            if len(r) > 0:
                AssetsDef.check_structure(r)
                result += [r]

        elif rodzaj_importu == 'assets.zloto-monety':
            r, gold_warnings = evaluate_zloto_monety(assets_file_row, valuation_date)
            for warning in gold_warnings:
                msg = f"[{asset_id}] {warning}"
                warnings.append(msg)
                print(f"OSTRZEZENIE {msg}")
            if not r.empty:
                AssetsDef.check_structure(r)
                result += [r]

        elif rodzaj_importu == KindDomain.BROKER or rodzaj_importu.startswith(KindDomain.BROKER + '.'):
            if is_obligacje_broker(assets_file_row):
                r, broker_warnings = evaluate_broker_obligacje(
                    data_root, asset_id, assets_file_row, valuation_date
                )
            else:
                r, broker_warnings = evaluate_broker_revolut(
                    data_root, asset_id, assets_file_row, valuation_date
                )
            for warning in broker_warnings:
                msg = f"[{asset_id}] {warning}"
                warnings.append(msg)
                print(f"OSTRZEZENIE {msg}")
            if not r.empty:
                AssetsDef.check_structure(r)
                result += [r]

        elif rodzaj_importu.startswith('assets.'):
            r = evaluate_assets_file(rodzaj_importu, assets_file_row, valuation_date)
            if r is not None and not r.empty:
                AssetsDef.check_structure(r)
                result += [r]
            elif r is None or r.empty:
                warnings.append(
                    f"[{asset_id}] Brak wyceny dla {rodzaj_importu!r} na date {valuation_date}."
                )

        else:
            msg = f"[{asset_id}] brakujący typ: {rodzaj_importu}"
            warnings.append(msg)
            print(msg)

    empty_cols = list(
        AssetsDef.expected_columns()
        | {LastFx.FX, AssetsDef.VALUE_PLN, AssetsDef.VALUE_DATE, AssetsDef.DAYS_AFTER_VALUATION}
    )
    if not result:
        return pd.DataFrame(columns=empty_cols), warnings

    result = pd.concat(result)
    AssetsDef.check_structure(result)

    last_fx = get_fx_as_of(fx_rates, valuation_date)

    result_fx = pd.merge(result, last_fx, on=AssetsDef.CURRENCY)
    assert len(result) == len(result_fx)

    mask = result_fx[AssetsDef.TYPE] == TypeDomain.CASH
    result_fx.loc[mask, AssetsDef.EVALUATION_DATE] = result_fx.loc[mask, AssetsDef.VALUE_DATE]

    result_fx[AssetsDef.VALUE_PLN] = result_fx[AssetsDef.VALUE] * result_fx[LastFx.FX]
    result_fx[AssetsDef.VALUE_PLN] = result_fx[AssetsDef.VALUE_PLN].round().astype('int')

    value_date = pd.to_datetime(result_fx[AssetsDef.VALUE_DATE], format="%Y-%m-%d")
    evaluation_date = pd.to_datetime(result_fx[AssetsDef.EVALUATION_DATE], format="%Y-%m-%d")
    diff = (value_date - evaluation_date).dt.days
    result_fx[AssetsDef.DAYS_AFTER_VALUATION] = diff
    return format_date_columns(result_fx, AssetsDef.EVALUATION_DATE, AssetsDef.VALUE_DATE), warnings
