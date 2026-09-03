# -*- coding: utf-8 -*-
"""Skład portfela 2 G-MOMENTUM: role, NAV, rozbicie pozycji/gotówki brokerów."""
from __future__ import annotations

from datetime import date

import pandas as pd

from evaluators.broker_snapshot import BrokerHoldings
from importers.assets.data_model import AssetsDef
from importers.degiro.data_model import DEFAULT_DEGIRO_ASSET_ID
from importers.xtb.data_model import DEFAULT_XTB_ASSET_ID
from portfolios.assignment import (
    PORTFOLIO_GM,
    PORTFOLIO_GM_ASSET_IDS,
    PORTFOLIO_GM_BROKER_ASSET_IDS,
    PORTFOLIO_GM_ORDER,
    ROLE_OVERLAY,
    gm_asset_role,
    nav_pln_for_portfolio,
)
from roi.gold_terminal import GOLD_COINS_ROI_ASSET_ID

_DISPLAY_NAMES = {
    DEFAULT_DEGIRO_ASSET_ID: "DEGIRO",
    DEFAULT_XTB_ASSET_ID: "XTB",
    GOLD_COINS_ROI_ASSET_ID: "złoto-monety",
}


def _component_label(asset_id: str) -> str:
    key = str(asset_id).strip()
    return _DISPLAY_NAMES.get(key, key)


def _numeric(value, default: float = 0.0) -> float:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return default
    return float(number)


def _rows_by_id(snapshot: pd.DataFrame) -> dict[str, pd.Series]:
    if snapshot is None or snapshot.empty or AssetsDef.ID not in snapshot.columns:
        return {}
    out: dict[str, pd.Series] = {}
    for _, row in snapshot.iterrows():
        key = str(row[AssetsDef.ID]).strip()
        if key in PORTFOLIO_GM_ASSET_IDS:
            out[key] = row
    return out


def _split_pln(
    asset_id: str,
    nav_pln: float,
    holdings: BrokerHoldings | None,
) -> tuple[float | None, float | None]:
    if gm_asset_role(asset_id) == ROLE_OVERLAY:
        if nav_pln == 0.0:
            return 0.0, 0.0
        return nav_pln, 0.0
    if holdings is None:
        return None, None
    total = holdings.total_value
    if total == 0:
        return 0.0, 0.0
    positions = nav_pln * float(holdings.positions_value) / total
    cash = nav_pln * float(holdings.cash_value) / total
    return positions, cash


def compose_gm_composition(
    snapshot: pd.DataFrame,
    holdings_by_id: dict[str, BrokerHoldings] | None = None,
) -> pd.DataFrame:
    holdings_by_id = holdings_by_id or {}
    by_id = _rows_by_id(snapshot)
    total = nav_pln_for_portfolio(snapshot, PORTFOLIO_GM)
    rows: list[dict[str, object]] = []
    for asset_id in PORTFOLIO_GM_ORDER:
        snap_row = by_id.get(asset_id)
        nav_pln = _numeric(snap_row.get(AssetsDef.VALUE_PLN)) if snap_row is not None else 0.0
        in_snapshot = snap_row is not None
        positions_pln, cash_pln = _split_pln(
            asset_id,
            nav_pln,
            holdings_by_id.get(asset_id),
        )
        weight = (nav_pln / total) if total else 0.0
        rows.append(
            {
                "id": asset_id,
                "Składnik": _component_label(asset_id),
                "Rola": gm_asset_role(asset_id),
                "NAV PLN": nav_pln,
                "Udział": weight,
                "Pozycje PLN": positions_pln,
                "Gotówka PLN": cash_pln,
                "w_snapshocie": in_snapshot,
            }
        )
    return pd.DataFrame(rows)


def load_gm_broker_holdings(
    valuation_date: date,
) -> tuple[dict[str, BrokerHoldings], list[str]]:
    from app_proc.data_root import get_online_data_root
    from evaluators.broker_registry import resolve_broker_snapshot_evaluator
    from importers.assets.read_assets import read_assets

    warnings: list[str] = []
    holdings: dict[str, BrokerHoldings] = {}
    try:
        catalog = read_assets()
        data_root = get_online_data_root()
    except Exception as exc:
        return {}, [f"Nie udało się wczytać katalogu / holdings portfela {PORTFOLIO_GM}: {exc}"]

    if catalog.empty or AssetsDef.ID not in catalog.columns:
        return {}, ["Brak katalogu aktywów do rozbicia pozycji/gotówki GM."]

    for asset_id in PORTFOLIO_GM_BROKER_ASSET_IDS:
        rows = catalog[catalog[AssetsDef.ID].astype(str).str.strip() == asset_id]
        if rows.empty:
            warnings.append(f"Brak {asset_id} w katalogu — bez rozbicia pozycji/gotówki.")
            continue
        row = rows.iloc[0]
        evaluator = resolve_broker_snapshot_evaluator(row)
        if evaluator is None:
            warnings.append(f"Brak ewaluatora holdings dla {asset_id}.")
            continue
        loaded, extra = evaluator.load_holdings(
            data_root, asset_id, row, valuation_date
        )
        warnings.extend(extra)
        if loaded is not None:
            holdings[asset_id] = loaded
    return holdings, warnings
