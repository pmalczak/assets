# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from app_proc.data_root import resolve_asset_dir
from evaluators.valuation_date import format_date_columns
from importers.assets.data_model import AssetsDef, GroupDomain, TypeDomain
from importers.degiro.data_model import DEFAULT_DEGIRO_ASSET_ID, DegiroPortfolioFile
from importers.degiro.read_degiro import latest_portfolio_as_of, read_degiro_portfolio


def is_degiro_broker(assets_file_row: pd.Series) -> bool:
    return str(assets_file_row.get(AssetsDef.ID, "")).strip() == DEFAULT_DEGIRO_ASSET_ID


def evaluate_broker_degiro(
    data_root: Path,
    asset_id: str,
    assets_file_row: pd.Series,
    valuation_date: date,
) -> tuple[pd.DataFrame, list[str]]:
    """Syntetyczna wycena rachunku DEGIRO: jeden wiersz = MTM z Portfolio.csv."""
    p = resolve_asset_dir(asset_id, assets_file_row[AssetsDef.TYPE])
    warnings: list[str] = []
    if not p.is_dir():
        warnings.append(
            f"Brak katalogu {p} — uruchom Import wyciągów "
            f"(Portfolio.csv/Transactions.csv/Account.csv → assets/{asset_id}/)."
        )
        return pd.DataFrame(columns=list(AssetsDef.expected_columns())), warnings

    portfolio = latest_portfolio_as_of(read_degiro_portfolio(p, asset_id), valuation_date)
    if portfolio.empty:
        warnings.append(f"Brak portfolio DEGIRO <= {valuation_date.isoformat()}.")
        return pd.DataFrame(columns=list(AssetsDef.expected_columns())), warnings

    total_value = float(pd.to_numeric(portfolio[DegiroPortfolioFile.VALUE_EUR], errors="coerce").fillna(0).sum())
    position_rows = portfolio[
        portfolio[DegiroPortfolioFile.ISIN].notna()
        & portfolio[DegiroPortfolioFile.ISIN].astype(str).str.strip().ne("")
    ]
    cash_rows = len(portfolio) - len(position_rows)

    row = AssetsDef.as_assets_row(assets_file_row)
    row[AssetsDef.VALUE] = total_value
    row[AssetsDef.EVALUATION_DATE] = str(portfolio[DegiroPortfolioFile.PERIOD_END].max())
    row[AssetsDef.TYPE] = TypeDomain.EQUITIES
    row[AssetsDef.GROUP] = GroupDomain.INVESTMENT
    row[AssetsDef.CURRENCY] = "EUR"
    base_descr = str(assets_file_row.get(AssetsDef.DESCR) or asset_id).strip() or asset_id
    row[AssetsDef.DESCR] = f"{base_descr} ({len(position_rows)} poz. + {cash_rows} cash)"

    result = pd.DataFrame([row])
    AssetsDef.check_structure(result)
    return format_date_columns(result, AssetsDef.EVALUATION_DATE), warnings
