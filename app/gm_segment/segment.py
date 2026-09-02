# -*- coding: utf-8 -*-
"""Portfel 2 G-MOMENTUM: widok na DEGIRO + XTB + złoto, nie nowe aktywo katalogowe."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from evaluators.broker_snapshot import BrokerHoldings
from importers.assets.data_model import AssetsDef
from importers.degiro.data_model import DEFAULT_DEGIRO_ASSET_ID
from importers.xtb.data_model import DEFAULT_XTB_ASSET_ID
from portfolios.assignment import PORTFOLIO_GM, PORTFOLIO_GM_ASSET_IDS, PORTFOLIO_GM_ORDER
from roi.gold_terminal import GOLD_COINS_ROI_ASSET_ID

GM_SEGMENT = PORTFOLIO_GM
ROLE_EXECUTION = "wykonanie"
ROLE_OVERLAY = "overlay"

GM_SEGMENT_ORDER = PORTFOLIO_GM_ORDER
GM_BROKER_ASSET_IDS = frozenset({DEFAULT_DEGIRO_ASSET_ID, DEFAULT_XTB_ASSET_ID})
GM_OVERLAY_ASSET_IDS = frozenset({GOLD_COINS_ROI_ASSET_ID})
GM_SEGMENT_ASSET_IDS = PORTFOLIO_GM_ASSET_IDS

_DISPLAY_NAMES = {
    DEFAULT_DEGIRO_ASSET_ID: "DEGIRO",
    DEFAULT_XTB_ASSET_ID: "XTB",
    GOLD_COINS_ROI_ASSET_ID: "złoto-monety",
}
_NAV_SERIES_NAME = f"Portfel {PORTFOLIO_GM} NAV"


def segment_for_asset_id(asset_id: str | None) -> str | None:
    if str(asset_id or "").strip() in GM_SEGMENT_ASSET_IDS:
        return GM_SEGMENT
    return None


def gm_segment_role(asset_id: str | None) -> str | None:
    key = str(asset_id or "").strip()
    if key in GM_OVERLAY_ASSET_IDS:
        return ROLE_OVERLAY
    if key in GM_BROKER_ASSET_IDS:
        return ROLE_EXECUTION
    return None


def display_name(asset_id: str) -> str:
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
        if key in GM_SEGMENT_ASSET_IDS:
            out[key] = row
    return out


def gm_segment_nav_pln(snapshot: pd.DataFrame) -> float:
    by_id = _rows_by_id(snapshot)
    return sum(_numeric(row.get(AssetsDef.VALUE_PLN)) for row in by_id.values())


def _split_pln(
    asset_id: str,
    nav_pln: float,
    holdings: BrokerHoldings | None,
) -> tuple[float | None, float | None]:
    if gm_segment_role(asset_id) == ROLE_OVERLAY:
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


def compose_gm_segment_table(
    snapshot: pd.DataFrame,
    holdings_by_id: dict[str, BrokerHoldings] | None = None,
) -> pd.DataFrame:
    holdings_by_id = holdings_by_id or {}
    by_id = _rows_by_id(snapshot)
    total = gm_segment_nav_pln(snapshot)
    rows: list[dict[str, object]] = []
    for asset_id in GM_SEGMENT_ORDER:
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
                "Składnik": display_name(asset_id),
                "Rola": gm_segment_role(asset_id),
                "NAV PLN": nav_pln,
                "Udział": weight,
                "Pozycje PLN": positions_pln,
                "Gotówka PLN": cash_pln,
                "w_snapshocie": in_snapshot,
            }
        )
    return pd.DataFrame(rows)


def load_gm_segment_nav_history(snapshots_dir: Path | None = None) -> pd.Series:
    from portfolios.assignment import load_portfolio_nav_history

    return load_portfolio_nav_history(PORTFOLIO_GM, snapshots_dir).rename(_NAV_SERIES_NAME)


def _drawdown(equity: pd.Series) -> pd.Series:
    return equity / equity.cummax() - 1


def nav_path_metrics(nav: pd.Series) -> dict[str, float]:
    clean = pd.to_numeric(nav, errors="coerce").dropna()
    clean = clean[clean > 0]
    if len(clean) < 2:
        return {}
    start = float(clean.iloc[0])
    end = float(clean.iloc[-1])
    days = (clean.index[-1] - clean.index[0]).days
    years = days / 365.25 if days > 0 else 0.0
    total_return = end / start - 1.0
    metrics = {
        "Total Return": total_return,
        "Max Drawdown": float(_drawdown(clean).min()),
        "Start": start,
        "End": end,
    }
    if years > 0:
        metrics["CAGR"] = (end / start) ** (1.0 / years) - 1.0
    return metrics


def rebased_overlap(left: pd.Series, right: pd.Series) -> pd.DataFrame:
    a = pd.to_numeric(left, errors="coerce").dropna()
    b = pd.to_numeric(right, errors="coerce").dropna()
    a.index = pd.to_datetime(a.index)
    b.index = pd.to_datetime(b.index)
    if a.empty or b.empty:
        return pd.DataFrame()
    start = max(a.index.min(), b.index.min())
    end = min(a.index.max(), b.index.max())
    if start > end:
        return pd.DataFrame()
    idx = a.index.union(b.index).sort_values()
    idx = idx[(idx >= start) & (idx <= end)]
    combined = pd.DataFrame(
        {
            str(a.name or "left"): a.reindex(idx).ffill(),
            str(b.name or "right"): b.reindex(idx).ffill(),
        }
    ).dropna()
    if combined.empty:
        return combined
    return combined / combined.iloc[0] * 100.0


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

    for asset_id in GM_BROKER_ASSET_IDS:
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
