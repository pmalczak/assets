# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from datetime import date
from pathlib import Path

import pandas as pd

from fx.data_model import LastFx
from importers.assets.data_model import AssetsDef, KindDomain, TypeDomain
from evaluators.evaluate_assets_file import evaluate_assets_file
from evaluators.broker_registry import resolve_broker_snapshot_evaluator
from evaluators.broker_snapshot import empty_broker_snapshot, unknown_broker_warning
from evaluators.evaluate_broker_obligacje import evaluate_broker_obligacje, is_obligacje_broker
from evaluators.evaluate_mbank import evaluate_mbank
from evaluators.evaluate_revolut import evaluate_revolut
from evaluators.evaluate_zloto_monety import evaluate_zloto_monety
from evaluators.valuation_date import format_date_columns
from fx.get_last_fx import get_fx_as_of
from portfolios.assignment import attach_portfolio_column


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
    frames, warnings = _dispatch_asset_evaluators(data_root, assets, valuation_date)
    return finalize_assets_with_fx(frames, fx_rates, valuation_date, warnings)


def _dispatch_asset_evaluators(
    data_root: Path,
    assets: pd.DataFrame,
    valuation_date: date,
) -> tuple[list[pd.DataFrame], list[str]]:
    result: list[pd.DataFrame] = []
    warnings: list[str] = []
    a = assets[assets[AssetsDef.KIND].notnull()]
    for _, assets_file_row in a.iterrows():
        assert isinstance(assets_file_row, pd.Series)
        rodzaj_importu: str = assets_file_row[AssetsDef.KIND]
        asset_id = str(assets_file_row[AssetsDef.ID])

        if rodzaj_importu.startswith(KindDomain.MBANK):
            r = evaluate_mbank(data_root, asset_id, assets_file_row, valuation_date)
            if not r.empty:
                AssetsDef.check_structure(r)
                result.append(r)

        elif rodzaj_importu.startswith(KindDomain.REVOLUT):
            r = evaluate_revolut(asset_id, assets_file_row, valuation_date)
            if len(r) > 0:
                AssetsDef.check_structure(r)
                result.append(r)

        elif rodzaj_importu == "assets.zloto-monety":
            r, gold_warnings = evaluate_zloto_monety(assets_file_row, valuation_date)
            _collect_warnings(warnings, asset_id, gold_warnings)
            if not r.empty:
                AssetsDef.check_structure(r)
                result.append(r)

        elif rodzaj_importu == KindDomain.BROKER or rodzaj_importu.startswith(KindDomain.BROKER + "."):
            if is_obligacje_broker(assets_file_row):
                r, broker_warnings = evaluate_broker_obligacje(
                    data_root, asset_id, assets_file_row, valuation_date
                )
            else:
                evaluator = resolve_broker_snapshot_evaluator(assets_file_row)
                if evaluator is None:
                    r = empty_broker_snapshot()
                    broker_warnings = [unknown_broker_warning(asset_id)]
                else:
                    r, broker_warnings = evaluator.evaluate(
                        data_root, asset_id, assets_file_row, valuation_date
                    )
            _collect_warnings(warnings, asset_id, broker_warnings)
            if not r.empty:
                AssetsDef.check_structure(r)
                result.append(r)

        elif rodzaj_importu.startswith("assets."):
            r = evaluate_assets_file(rodzaj_importu, assets_file_row, valuation_date)
            if r is not None and not r.empty:
                AssetsDef.check_structure(r)
                result.append(r)
            elif r is None or r.empty:
                warnings.append(
                    f"[{asset_id}] Brak wyceny dla {rodzaj_importu!r} na date {valuation_date}."
                )

        else:
            msg = f"[{asset_id}] brakujący typ: {rodzaj_importu}"
            warnings.append(msg)
            print(msg)

    return result, warnings


def finalize_assets_with_fx(
    frames: list[pd.DataFrame],
    fx_rates: pd.DataFrame,
    valuation_date: date,
    warnings: list[str] | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Merge FX, VALUE_PLN, cash-pool days, portfolio column, ISO date columns."""
    warnings = list(warnings or [])
    empty_cols = list(
        AssetsDef.expected_columns()
        | {
            LastFx.FX,
            AssetsDef.VALUE_PLN,
            AssetsDef.VALUE_DATE,
            AssetsDef.DAYS_AFTER_VALUATION,
            AssetsDef.STATEMENT_DATE,
            AssetsDef.LAST_TRANSACTION_DATE,
        }
    )
    if not frames:
        return pd.DataFrame(columns=empty_cols), warnings

    result = pd.concat(frames)
    AssetsDef.check_structure(result)

    last_fx = get_fx_as_of(fx_rates, valuation_date)
    result_fx = pd.merge(result, last_fx, on=AssetsDef.CURRENCY)
    assert len(result) == len(result_fx)

    mask = result_fx[AssetsDef.TYPE] == TypeDomain.CASH
    result_fx.loc[mask, AssetsDef.EVALUATION_DATE] = result_fx.loc[mask, AssetsDef.VALUE_DATE]

    result_fx[AssetsDef.VALUE_PLN] = result_fx[AssetsDef.VALUE] * result_fx[LastFx.FX]
    result_fx[AssetsDef.VALUE_PLN] = result_fx[AssetsDef.VALUE_PLN].round().astype("int")

    result_fx = attach_portfolio_column(result_fx)
    result_fx[AssetsDef.DAYS_AFTER_VALUATION] = _days_after_valuation(result_fx)
    return format_date_columns(
        result_fx,
        AssetsDef.EVALUATION_DATE,
        AssetsDef.VALUE_DATE,
        AssetsDef.STATEMENT_DATE,
        AssetsDef.LAST_TRANSACTION_DATE,
    ), warnings


def _days_after_valuation(result_fx: pd.DataFrame) -> pd.Series:
    """Domyślnie data-waluty − data wyceny; cash_pool.ror: data-waluty − data-wyciągu."""
    value_date = pd.to_datetime(result_fx[AssetsDef.VALUE_DATE], format="%Y-%m-%d")
    evaluation_date = pd.to_datetime(result_fx[AssetsDef.EVALUATION_DATE], format="%Y-%m-%d")
    diff = (value_date - evaluation_date).dt.days
    cash_pool_mask = result_fx[AssetsDef.TYPE] == TypeDomain.CURRENT_ACCOUNT
    if AssetsDef.STATEMENT_DATE in result_fx.columns and cash_pool_mask.any():
        statement_date = pd.to_datetime(
            result_fx.loc[cash_pool_mask, AssetsDef.STATEMENT_DATE], format="%Y-%m-%d"
        )
        diff.loc[cash_pool_mask] = (value_date.loc[cash_pool_mask] - statement_date).dt.days
    return diff


def _collect_warnings(warnings: list[str], asset_id: str, messages: list[str]) -> None:
    for warning in messages:
        msg = f"[{asset_id}] {warning}"
        warnings.append(msg)
        print(f"OSTRZEZENIE {msg}")
