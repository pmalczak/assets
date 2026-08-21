# -*- coding: utf-8 -*-
"""Wspólny snapshot brokera: VALUE = pozycje + gotówka robocza."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from evaluators.valuation_date import format_date_columns
from importers.assets.data_model import AssetsDef, GroupDomain, TypeDomain


def empty_broker_snapshot() -> pd.DataFrame:
    return pd.DataFrame(columns=list(AssetsDef.expected_columns()))


@dataclass(frozen=True)
class BrokerHoldings:
    """Wycena kontenera. `cash_value` jest wymagane — 0, gdy na rachunku nie ma gotówki."""

    positions_value: float
    cash_value: float
    n_positions: int
    n_cash_rows: int
    evaluation_date: str
    currency: str | None = None

    @property
    def total_value(self) -> float:
        return float(self.positions_value) + float(self.cash_value)

    def describe(self, base: str) -> str:
        return f"{base} ({self.n_positions} poz. + {self.n_cash_rows} cash)"


def snapshot_from_holdings(
    assets_file_row: pd.Series,
    asset_id: str,
    holdings: BrokerHoldings,
) -> pd.DataFrame:
    row = AssetsDef.as_assets_row(assets_file_row)
    row[AssetsDef.VALUE] = holdings.total_value
    row[AssetsDef.EVALUATION_DATE] = holdings.evaluation_date
    row[AssetsDef.TYPE] = TypeDomain.EQUITIES
    row[AssetsDef.GROUP] = GroupDomain.INVESTMENT
    base_descr = str(assets_file_row.get(AssetsDef.DESCR) or asset_id).strip() or asset_id
    row[AssetsDef.DESCR] = holdings.describe(base_descr)
    if holdings.currency:
        row[AssetsDef.CURRENCY] = holdings.currency
    result = pd.DataFrame([row])
    AssetsDef.check_structure(result)
    return format_date_columns(result, AssetsDef.EVALUATION_DATE)


class BrokerSnapshotEvaluator(ABC):
    """
    Nowy broker udziałowy: podklasa + wpis w `BROKER_SNAPSHOT_EVALUATORS`.
    Szablon `evaluate` zawsze składa VALUE z `positions_value + cash_value`.
    Obligacje PKO są poza tym kontraktem (MTM papierów, inny `typ`).
    """

    @abstractmethod
    def matches(self, assets_file_row: pd.Series) -> bool:
        raise NotImplementedError

    @abstractmethod
    def load_holdings(
        self,
        data_root: Path,
        asset_id: str,
        assets_file_row: pd.Series,
        valuation_date: date,
    ) -> tuple[BrokerHoldings | None, list[str]]:
        """None = brak wiersza (brak katalogu/raportu). `cash_value` podać nawet gdy 0."""
        raise NotImplementedError

    def evaluate(
        self,
        data_root: Path,
        asset_id: str,
        assets_file_row: pd.Series,
        valuation_date: date,
    ) -> tuple[pd.DataFrame, list[str]]:
        holdings, warnings = self.load_holdings(
            data_root, asset_id, assets_file_row, valuation_date
        )
        if holdings is None:
            return empty_broker_snapshot(), warnings
        return snapshot_from_holdings(assets_file_row, asset_id, holdings), warnings


def unknown_broker_warning(asset_id: str) -> str:
    return (
        f"Nieznany broker {asset_id!r}: dodaj podklasę BrokerSnapshotEvaluator "
        f"(snapshot = pozycje + gotówka) i zarejestruj ją w BROKER_SNAPSHOT_EVALUATORS."
    )
