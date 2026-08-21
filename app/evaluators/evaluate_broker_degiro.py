# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from app_proc.data_root import resolve_asset_dir
from evaluators.broker_snapshot import BrokerHoldings, BrokerSnapshotEvaluator
from importers.assets.data_model import AssetsDef
from importers.degiro.data_model import DEFAULT_DEGIRO_ASSET_ID, DegiroPortfolioFile
from importers.degiro.read_degiro import latest_portfolio_as_of, read_degiro_portfolio


def is_degiro_broker(assets_file_row: pd.Series) -> bool:
    return str(assets_file_row.get(AssetsDef.ID, "")).strip() == DEFAULT_DEGIRO_ASSET_ID


class DegiroSnapshotEvaluator(BrokerSnapshotEvaluator):
    def matches(self, assets_file_row: pd.Series) -> bool:
        return is_degiro_broker(assets_file_row)

    def load_holdings(
        self,
        data_root: Path,
        asset_id: str,
        assets_file_row: pd.Series,
        valuation_date: date,
    ) -> tuple[BrokerHoldings | None, list[str]]:
        p = resolve_asset_dir(asset_id, assets_file_row[AssetsDef.TYPE])
        warnings: list[str] = []
        if not p.is_dir():
            warnings.append(
                f"Brak katalogu {p} — uruchom Import wyciągów "
                f"(Portfolio.csv/Transactions.csv/Account.csv → assets/{asset_id}/)."
            )
            return None, warnings

        portfolio = latest_portfolio_as_of(read_degiro_portfolio(p, asset_id), valuation_date)
        if portfolio.empty:
            warnings.append(f"Brak portfolio DEGIRO <= {valuation_date.isoformat()}.")
            return None, warnings

        isin = portfolio[DegiroPortfolioFile.ISIN]
        has_isin = isin.notna() & isin.astype(str).str.strip().ne("")
        position_rows = portfolio.loc[has_isin]
        cash_rows = portfolio.loc[~has_isin]
        return (
            BrokerHoldings(
                positions_value=_eur_sum(position_rows),
                cash_value=_eur_sum(cash_rows),
                n_positions=len(position_rows),
                n_cash_rows=len(cash_rows),
                evaluation_date=str(portfolio[DegiroPortfolioFile.PERIOD_END].max()),
                currency="EUR",
            ),
            warnings,
        )


def evaluate_broker_degiro(
    data_root: Path,
    asset_id: str,
    assets_file_row: pd.Series,
    valuation_date: date,
) -> tuple[pd.DataFrame, list[str]]:
    """Syntetyczna wycena rachunku DEGIRO: jeden wiersz = MTM z Portfolio.csv."""
    return DegiroSnapshotEvaluator().evaluate(
        data_root, asset_id, assets_file_row, valuation_date
    )


def _eur_sum(df: pd.DataFrame) -> float:
    if df.empty or DegiroPortfolioFile.VALUE_EUR not in df.columns:
        return 0.0
    return float(
        pd.to_numeric(df[DegiroPortfolioFile.VALUE_EUR], errors="coerce").fillna(0).sum()
    )
