# -*- coding: utf-8 -*-
"""Przypisanie aktywów do portfela (0 OGÓLNY / 1 REVOLUT-ROBO / 2 G-MOMENTUM)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from importers.assets.data_model import AssetsDef
from importers.degiro.data_model import DEFAULT_DEGIRO_ASSET_ID
from importers.revolut.trading_data_model import DEFAULT_REVOLUT_ROBO_ASSET_ID
from importers.xtb.data_model import DEFAULT_XTB_ASSET_ID
from roi.gold_terminal import GOLD_COINS_ROI_ASSET_ID

PORTFOLIO_OGOLNY = "0 OGÓLNY"
PORTFOLIO_REVOLUT_ROBO = "1 REVOLUT-ROBO"
PORTFOLIO_GM = "2 G-MOMENTUM"
DEFAULT_PORTFOLIO = PORTFOLIO_OGOLNY

PORTFOLIO_GM_ORDER: tuple[str, ...] = (
    DEFAULT_DEGIRO_ASSET_ID,
    DEFAULT_XTB_ASSET_ID,
    GOLD_COINS_ROI_ASSET_ID,
)
PORTFOLIO_GM_ASSET_IDS = frozenset(PORTFOLIO_GM_ORDER)
PORTFOLIO_GM_BROKER_ASSET_IDS = frozenset({DEFAULT_DEGIRO_ASSET_ID, DEFAULT_XTB_ASSET_ID})
PORTFOLIO_GM_OVERLAY_ASSET_IDS = frozenset({GOLD_COINS_ROI_ASSET_ID})
PORTFOLIO_REVOLUT_ROBO_ASSET_IDS = frozenset({DEFAULT_REVOLUT_ROBO_ASSET_ID})

ROLE_EXECUTION = "wykonanie"
ROLE_OVERLAY = "overlay"

KNOWN_PORTFOLIOS: tuple[str, ...] = (
    PORTFOLIO_OGOLNY,
    PORTFOLIO_REVOLUT_ROBO,
    PORTFOLIO_GM,
)


def portfolio_for_asset_id(asset_id: str | None) -> str:
    key = str(asset_id or "").strip()
    if key in PORTFOLIO_GM_ASSET_IDS:
        return PORTFOLIO_GM
    if key in PORTFOLIO_REVOLUT_ROBO_ASSET_IDS:
        return PORTFOLIO_REVOLUT_ROBO
    return DEFAULT_PORTFOLIO


def gm_asset_role(asset_id: str | None) -> str | None:
    """Rola składnika w portfelu 2 G-MOMENTUM: wykonanie U7 vs overlay (złoto)."""
    key = str(asset_id or "").strip()
    if key in PORTFOLIO_GM_OVERLAY_ASSET_IDS:
        return ROLE_OVERLAY
    if key in PORTFOLIO_GM_BROKER_ASSET_IDS:
        return ROLE_EXECUTION
    return None


def portfolio_for_row(asset_id: str | None, typ: str | None) -> str:
    kind = str(typ or "").strip()
    if kind.startswith("cash_pool.") or kind.startswith("investment."):
        return portfolio_for_asset_id(asset_id)
    if not kind:
        return portfolio_for_asset_id(asset_id)
    return ""


def attach_portfolio_column(assets: pd.DataFrame) -> pd.DataFrame:
    """Dopisz / nadpisz kolumnę `portfel` wg id i `typ` (stare snapshoty bez kolumny)."""
    if assets is None or assets.empty:
        return assets
    if AssetsDef.ID not in assets.columns:
        return assets
    out = assets.copy()
    asset_ids = out[AssetsDef.ID]
    if AssetsDef.TYPE in out.columns:
        types = out[AssetsDef.TYPE]
    else:
        types = [""] * len(out)
    out[AssetsDef.PORTFOLIO] = [
        portfolio_for_row(asset_id, type_value)
        for asset_id, type_value in zip(asset_ids, types)
    ]
    return out


def rows_with_portfolio(assets: pd.DataFrame, type_prefix: str | None = None) -> pd.DataFrame:
    if assets is None or assets.empty:
        return assets.copy() if assets is not None else pd.DataFrame()
    work = attach_portfolio_column(assets)
    if type_prefix:
        if AssetsDef.TYPE not in work.columns:
            return work.iloc[0:0].copy()
        typ = work[AssetsDef.TYPE].astype(str)
        work = work.loc[typ.str.startswith(type_prefix)].copy()
    return _portfolio_after_group(work)


def investments_with_portfolio(assets: pd.DataFrame) -> pd.DataFrame:
    return rows_with_portfolio(assets, "investment.")


def investments_by_portfolio(assets: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    """Inwestycje w kolejności KNOWN_PORTFOLIOS; kolumna `portfel` zbędna w każdej tabeli."""
    work = investments_with_portfolio(assets)
    if work is None:
        work = pd.DataFrame()
    tables: list[tuple[str, pd.DataFrame]] = []
    for name in KNOWN_PORTFOLIOS:
        if AssetsDef.PORTFOLIO in work.columns:
            part = work.loc[work[AssetsDef.PORTFOLIO] == name].drop(
                columns=[AssetsDef.PORTFOLIO]
            )
        else:
            part = work.iloc[0:0].copy()
        tables.append((name, part))
    return tables


def _portfolio_after_group(df: pd.DataFrame) -> pd.DataFrame:
    if AssetsDef.PORTFOLIO not in df.columns:
        return df
    cols = [c for c in df.columns if c != AssetsDef.PORTFOLIO]
    if AssetsDef.GROUP in cols:
        insert_at = cols.index(AssetsDef.GROUP) + 1
    elif AssetsDef.ID in cols:
        insert_at = cols.index(AssetsDef.ID) + 1
    else:
        insert_at = 0
    cols.insert(insert_at, AssetsDef.PORTFOLIO)
    return df[cols]


def portfolio_nav_pln(assets: pd.DataFrame) -> pd.DataFrame:
    stamped = attach_portfolio_column(assets)
    if stamped is None or stamped.empty or AssetsDef.VALUE_PLN not in stamped.columns:
        return pd.DataFrame(columns=[AssetsDef.PORTFOLIO, AssetsDef.VALUE_PLN])
    has_portfolio = stamped[AssetsDef.PORTFOLIO].astype(str).str.strip().ne("")
    stamped = stamped.loc[has_portfolio]
    value = pd.to_numeric(stamped[AssetsDef.VALUE_PLN], errors="coerce").fillna(0)
    summary = (
        stamped.assign(_nav=value)
        .groupby(AssetsDef.PORTFOLIO, dropna=False)["_nav"]
        .sum()
        .rename(AssetsDef.VALUE_PLN)
        .reindex(list(KNOWN_PORTFOLIOS), fill_value=0)
        .reset_index()
    )
    return summary


def nav_pln_for_portfolio(assets: pd.DataFrame, portfolio_name: str) -> float:
    summary = portfolio_nav_pln(assets)
    if summary is None or summary.empty:
        return 0.0
    matched = summary.loc[summary[AssetsDef.PORTFOLIO].astype(str) == str(portfolio_name)]
    if matched.empty:
        return 0.0
    return float(pd.to_numeric(matched[AssetsDef.VALUE_PLN], errors="coerce").fillna(0).iloc[0])


def assets_in_portfolio(assets: pd.DataFrame, portfolio_name: str) -> pd.DataFrame:
    """Wiersze snapshotu przypisane do nazwanego portfela (inwestycje i cash pool)."""
    work = rows_with_portfolio(assets)
    if work is None or work.empty or AssetsDef.PORTFOLIO not in work.columns:
        return pd.DataFrame()
    part = work.loc[work[AssetsDef.PORTFOLIO].astype(str) == str(portfolio_name)].copy()
    return part


def load_portfolio_nav_history(
    portfolio_name: str,
    snapshots_dir: Path | None = None,
) -> pd.Series:
    """Suma VALUE_PLN ze snapshotów `09 assets` dla jednego nazwanego portfela."""
    from app_proc.snapshots import list_snapshot_files, load_snapshot, snapshots_directory

    directory = snapshots_dir if snapshots_dir is not None else snapshots_directory()
    dates: list[pd.Timestamp] = []
    values: list[float] = []
    preferred = [AssetsDef.ID, AssetsDef.TYPE, AssetsDef.VALUE_PLN]
    fallback = [AssetsDef.ID, AssetsDef.VALUE_PLN]
    for snapshot_date, path in list_snapshot_files(directory):
        try:
            assets = pd.read_parquet(path, columns=preferred)
        except Exception:
            try:
                assets = pd.read_parquet(path, columns=fallback)
            except Exception:
                assets = load_snapshot(path)
        dates.append(pd.Timestamp(snapshot_date))
        values.append(nav_pln_for_portfolio(assets, portfolio_name))
    series = pd.Series(
        values,
        index=pd.DatetimeIndex(dates),
        name=f"Portfel {portfolio_name} NAV",
    )
    if series.empty:
        return series
    return series.sort_index()
