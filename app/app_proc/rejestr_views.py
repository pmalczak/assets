# -*- coding: utf-8 -*-
"""Ramki Stan / Ruchy dla zakładki Rejestr (podgląd qty)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from importers.assets.data_model import AssetsDef, Inventory
from importers.assets.ike import IkeInventory, IkeKurs, read_ike_inventory, read_ike_kurs
from importers.assets.read_assets import read_assets, read_inventory
from evaluators.valuation_date import filter_excel_rows_on_or_before
from roi.gold_terminal import holdings_from_inventory


ASSET_ZLOTO = "Złoto"
ASSET_IKE_PM = "IKE PM"
ASSET_IKE_GM = "IKE GM"
ASSET_OBLIGACJE = "Obligacje"
ASSET_DEGIRO = "DEGIRO"
ASSET_XTB = "XTB"
ASSET_ROBO = "Robo"

REJESTR_ASSETS = [
    ASSET_ZLOTO,
    ASSET_IKE_PM,
    ASSET_IKE_GM,
    ASSET_OBLIGACJE,
    ASSET_DEGIRO,
    ASSET_XTB,
    ASSET_ROBO,
]

LAYER_STAN = "Stan"
LAYER_RUCHY = "Ruchy"

_OBLIGACJE_ID = "obligacjeskarbowe"


@dataclass
class RejestrLayer:
    frame: pd.DataFrame
    n_positions: int = 0
    total_value: float | None = None
    value_currency: str | None = None
    as_of: str | None = None
    extra: dict[str, str | int | float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class RejestrAssetView:
    asset: str
    has_ruchy: bool
    stan: RejestrLayer
    ruchy: RejestrLayer | None = None


def build_rejestr_asset(asset: str, as_of: date | None = None) -> RejestrAssetView:
    day = as_of or date.today()
    if asset == ASSET_ZLOTO:
        return _gold_view(day)
    if asset == ASSET_IKE_PM:
        return _ike_view("pm", day)
    if asset == ASSET_IKE_GM:
        return _ike_view("gm", day)
    if asset == ASSET_OBLIGACJE:
        return _obligacje_view(day)
    if asset == ASSET_DEGIRO:
        return _degiro_view(day)
    if asset == ASSET_XTB:
        return _xtb_view(day)
    if asset == ASSET_ROBO:
        return _robo_view(day)
    raise ValueError(f"Nieznane aktywo Rejestr: {asset!r}")


def _gold_view(as_of: date) -> RejestrAssetView:
    inventory = read_inventory()
    holdings = holdings_from_inventory(inventory, as_of)
    stan_rows = [
        {
            Inventory.INSTRUMENT: name,
            Inventory.QUANTITY: qty,
            Inventory.WEIGHT: "1oz",
        }
        for name, qty in sorted(holdings.items())
        if abs(qty) > 1e-12
    ]
    stan_frame = pd.DataFrame(
        stan_rows,
        columns=[Inventory.INSTRUMENT, Inventory.QUANTITY, Inventory.WEIGHT],
    )
    total_qty = float(sum(holdings.values())) if holdings else 0.0
    stan = RejestrLayer(
        frame=stan_frame,
        n_positions=len(stan_frame),
        as_of=as_of.isoformat(),
        extra={"suma sztuk": total_qty},
    )

    ruchy_cols = [
        Inventory.DATE,
        Inventory.INSTRUMENT,
        Inventory.WEIGHT,
        Inventory.QUANTITY,
    ]
    if inventory is not None and not inventory.empty and Inventory.NOTES in inventory.columns:
        ruchy_cols.append(Inventory.NOTES)
    if inventory is None or inventory.empty:
        ruchy_frame = pd.DataFrame(columns=ruchy_cols)
    else:
        ruchy_frame = inventory.loc[:, [c for c in ruchy_cols if c in inventory.columns]].copy()
        ruchy_frame = ruchy_frame.sort_values(
            Inventory.DATE, ascending=False, na_position="last"
        ).reset_index(drop=True)
    ruchy = RejestrLayer(frame=ruchy_frame, n_positions=len(ruchy_frame), as_of=as_of.isoformat())
    return RejestrAssetView(asset=ASSET_ZLOTO, has_ruchy=True, stan=stan, ruchy=ruchy)


def _ike_holdings_frame(
    inventory: pd.DataFrame,
    kurs: pd.DataFrame,
    as_of: date,
) -> tuple[pd.DataFrame, float | None, date | None]:
    """Per Produkt: Σ jednostek, ostatni kurs ≤ as_of, NAV."""
    cols = [
        IkeInventory.PRODUCT,
        "jednostki",
        IkeKurs.PRICE,
        "data kursu",
        AssetsDef.VALUE,
        IkeInventory.CURRENCY,
    ]
    inv = filter_excel_rows_on_or_before(inventory, IkeInventory.DATE, as_of)
    if inv.empty:
        return pd.DataFrame(columns=cols), None, None

    inv = inv.copy()
    inv[IkeInventory.PRODUCT] = inv[IkeInventory.PRODUCT].astype(str)
    inv["_units"] = pd.to_numeric(inv[IkeInventory.UNITS], errors="coerce").fillna(0.0)

    if kurs is None or kurs.empty:
        raise ValueError(f"IKE: brak arkusza/wierszy kursu na {as_of.isoformat()}")
    prices_all = filter_excel_rows_on_or_before(kurs, IkeKurs.DATE, as_of)
    if prices_all.empty:
        raise ValueError(f"IKE: brak kursów ≤ {as_of.isoformat()}")

    rows: list[dict] = []
    eval_dates: list[date] = []
    total = 0.0
    for prod, group in inv.groupby(IkeInventory.PRODUCT, sort=True):
        qty = float(group["_units"].sum())
        if abs(qty) < 1e-12:
            continue
        prices = prices_all[prices_all[IkeKurs.PRODUCT].astype(str) == str(prod)]
        if prices.empty:
            raise ValueError(
                f"IKE: brak kursu dla {prod!r} na {as_of.isoformat()} (qty={qty})"
            )
        last = prices.sort_values(IkeKurs.DATE).iloc[-1]
        price = float(last[IkeKurs.PRICE])
        eval_ts = pd.Timestamp(last[IkeKurs.DATE])
        if pd.isna(eval_ts):
            raise ValueError(f"IKE: nieparsowalna data kursu dla {prod!r}")
        eval_d = eval_ts.date()
        nav = qty * price
        currency = ""
        if IkeInventory.CURRENCY in group.columns:
            cur = group[IkeInventory.CURRENCY].dropna()
            if not cur.empty:
                currency = str(cur.iloc[-1]).strip()
        rows.append(
            {
                IkeInventory.PRODUCT: prod,
                "jednostki": qty,
                IkeKurs.PRICE: price,
                "data kursu": eval_d.isoformat(),
                AssetsDef.VALUE: nav,
                IkeInventory.CURRENCY: currency or "PLN",
            }
        )
        total += nav
        eval_dates.append(eval_d)

    frame = pd.DataFrame(rows, columns=cols)
    eval_date = max(eval_dates) if eval_dates else None
    return frame, (total if rows else None), eval_date


def _ike_view(account: str, as_of: date) -> RejestrAssetView:
    label = ASSET_IKE_PM if account == "pm" else ASSET_IKE_GM
    inventory = read_ike_inventory(account)
    kurs = read_ike_kurs()
    stan_frame, total, eval_date = _ike_holdings_frame(inventory, kurs, as_of)
    currency = None
    if not stan_frame.empty and IkeInventory.CURRENCY in stan_frame.columns:
        currencies = stan_frame[IkeInventory.CURRENCY].dropna().astype(str).str.strip()
        currency = currencies.iloc[0] if not currencies.empty else "PLN"
    stan = RejestrLayer(
        frame=stan_frame,
        n_positions=len(stan_frame),
        total_value=total,
        value_currency=currency or "PLN",
        as_of=(eval_date or as_of).isoformat(),
    )

    ruchy_cols = [
        IkeInventory.DATE,
        IkeInventory.PRODUCT,
        IkeInventory.UNITS,
        IkeInventory.VALUE,
        IkeInventory.CURRENCY,
    ]
    if inventory is None or inventory.empty:
        ruchy_frame = pd.DataFrame(columns=ruchy_cols)
    else:
        ruchy_frame = inventory.loc[:, ruchy_cols].copy()
        ruchy_frame = ruchy_frame.sort_values(
            IkeInventory.DATE, ascending=False, na_position="last"
        ).reset_index(drop=True)
    ruchy = RejestrLayer(frame=ruchy_frame, n_positions=len(ruchy_frame))
    return RejestrAssetView(asset=label, has_ruchy=True, stan=stan, ruchy=ruchy)


def _catalog_row(asset_id: str) -> tuple[pd.Series | None, list[str]]:
    try:
        catalog = read_assets()
    except Exception as exc:
        return None, [f"Nie udało się wczytać katalogu: {exc}"]
    if catalog.empty or AssetsDef.ID not in catalog.columns:
        return None, ["Brak katalogu aktywów."]
    rows = catalog[catalog[AssetsDef.ID].astype(str).str.strip() == asset_id]
    if rows.empty:
        return None, [f"Brak {asset_id} w katalogu."]
    return rows.iloc[0], []


def _obligacje_view(as_of: date) -> RejestrAssetView:
    from app_proc.data_root import resolve_asset_dir
    from importers.pkobp.data_model import PkoBpBonds, PkoBpStan
    from importers.pkobp.read_historia import qty_signed_ops, read_obligacje_historia
    from importers.pkobp.read_stan import read_obligacje_stan, select_stan_as_of, stan_mtm_total

    warnings: list[str] = []
    row, cat_warnings = _catalog_row(_OBLIGACJE_ID)
    warnings.extend(cat_warnings)
    empty_stan = pd.DataFrame(
        columns=[
            PkoBpStan.EMISSION,
            PkoBpStan.QTY_AVAILABLE,
            PkoBpStan.QTY_BLOCKED,
            PkoBpStan.CURRENT_VALUE,
            PkoBpStan.UNIT_PRICE,
            PkoBpStan.MATURITY,
            PkoBpStan.FILE_DATE,
        ]
    )
    if row is None:
        return RejestrAssetView(
            asset=ASSET_OBLIGACJE,
            has_ruchy=True,
            stan=RejestrLayer(frame=empty_stan, warnings=warnings),
            ruchy=RejestrLayer(
                frame=pd.DataFrame(
                    columns=[
                        PkoBpBonds.DATE,
                        PkoBpBonds.CODE,
                        PkoBpBonds.ORDER_TYPE,
                        PkoBpBonds.BONDS_NO,
                    ]
                ),
                warnings=warnings,
            ),
        )

    typ = str(row.get(AssetsDef.TYPE) or "").strip()
    asset_dir = resolve_asset_dir(_OBLIGACJE_ID, typ)
    if not asset_dir.is_dir():
        warnings.append(f"Brak katalogu {asset_dir}.")
        return RejestrAssetView(
            asset=ASSET_OBLIGACJE,
            has_ruchy=True,
            stan=RejestrLayer(frame=empty_stan, warnings=warnings),
            ruchy=RejestrLayer(
                frame=pd.DataFrame(
                    columns=[
                        PkoBpBonds.DATE,
                        PkoBpBonds.CODE,
                        PkoBpBonds.ORDER_TYPE,
                        PkoBpBonds.BONDS_NO,
                    ]
                ),
                warnings=warnings,
            ),
        )

    stan_raw = read_obligacje_stan(asset_dir, _OBLIGACJE_ID)
    selected = select_stan_as_of(stan_raw, as_of)
    if selected.empty:
        stan_frame = empty_stan
        file_date = None
        total = None
    else:
        stan_frame = selected.loc[
            :,
            [
                PkoBpStan.EMISSION,
                PkoBpStan.QTY_AVAILABLE,
                PkoBpStan.QTY_BLOCKED,
                PkoBpStan.CURRENT_VALUE,
                PkoBpStan.UNIT_PRICE,
                PkoBpStan.MATURITY,
                PkoBpStan.FILE_DATE,
            ],
        ].copy()
        stan_frame = stan_frame.rename(columns={PkoBpStan.CURRENT_VALUE: AssetsDef.VALUE})
        file_date = str(selected[PkoBpStan.FILE_DATE].iloc[0])
        total = stan_mtm_total(selected)

    stan = RejestrLayer(
        frame=stan_frame,
        n_positions=len(stan_frame),
        total_value=total,
        value_currency="PLN",
        as_of=file_date or as_of.isoformat(),
        warnings=warnings,
    )

    historia = read_obligacje_historia(asset_dir, _OBLIGACJE_ID)
    ops = qty_signed_ops(historia)
    if ops.empty:
        ruchy_frame = pd.DataFrame(
            columns=[
                PkoBpBonds.DATE,
                PkoBpBonds.CODE,
                PkoBpBonds.ORDER_TYPE,
                PkoBpBonds.BONDS_NO,
            ]
        )
    else:
        ruchy_frame = ops.copy()
        ruchy_frame = ruchy_frame.sort_values(
            PkoBpBonds.DATE, ascending=False, na_position="last"
        ).reset_index(drop=True)
    ruchy = RejestrLayer(frame=ruchy_frame, n_positions=len(ruchy_frame), warnings=warnings)
    return RejestrAssetView(asset=ASSET_OBLIGACJE, has_ruchy=True, stan=stan, ruchy=ruchy)


def _instrument_name(mapping, *, venue: str, code: str, fallback: str) -> str:
    from importers.assets.instruments import InstrumentMapError

    if mapping is None or not code:
        return fallback or code
    try:
        if venue == "degiro":
            return mapping.instrument_for_degiro(code)
        if venue == "xtb":
            return mapping.instrument_for_xtb(code)
    except InstrumentMapError:
        pass
    return fallback or code


def _load_instrument_map_soft() -> tuple[object | None, list[str]]:
    from importers.assets.instruments import InstrumentMapError, load_instrument_map

    try:
        return load_instrument_map(), []
    except InstrumentMapError as exc:
        return None, [f"Brak mapowania instruments — nazwy ze źródła: {exc}"]


def _broker_stan_from_positions(
    positions: pd.DataFrame,
    *,
    venue: str,
    warnings: list[str],
) -> RejestrLayer:
    from importers.broker.data_model import BrokerPositionFrame

    mapping, map_warnings = _load_instrument_map_soft()
    warnings = list(warnings) + map_warnings
    if positions is None or positions.empty:
        return RejestrLayer(
            frame=pd.DataFrame(
                columns=[
                    "instrument",
                    BrokerPositionFrame.TICKER,
                    BrokerPositionFrame.ISIN,
                    BrokerPositionFrame.QUANTITY,
                    AssetsDef.VALUE,
                    BrokerPositionFrame.CURRENCY,
                    BrokerPositionFrame.AS_OF,
                ]
            ),
            warnings=warnings,
        )

    rows = []
    for _, row in positions.iterrows():
        qty = float(pd.to_numeric(row.get(BrokerPositionFrame.QUANTITY), errors="coerce") or 0.0)
        if abs(qty) < 1e-12:
            continue
        isin = str(row.get(BrokerPositionFrame.ISIN) or "").strip()
        ticker = str(row.get(BrokerPositionFrame.TICKER) or "").strip()
        product = str(row.get(BrokerPositionFrame.INSTRUMENT) or "").strip()
        code = isin if venue == "degiro" else (ticker or isin)
        name = _instrument_name(mapping, venue=venue, code=code, fallback=product or code)
        rows.append(
            {
                "instrument": name,
                BrokerPositionFrame.TICKER: ticker,
                BrokerPositionFrame.ISIN: isin,
                BrokerPositionFrame.QUANTITY: qty,
                AssetsDef.VALUE: float(
                    pd.to_numeric(row.get(BrokerPositionFrame.MARKET_VALUE), errors="coerce") or 0.0
                ),
                BrokerPositionFrame.CURRENCY: str(row.get(BrokerPositionFrame.CURRENCY) or "").strip(),
                BrokerPositionFrame.AS_OF: str(row.get(BrokerPositionFrame.AS_OF) or ""),
            }
        )
    frame = pd.DataFrame(rows)
    as_of = None
    if not frame.empty and BrokerPositionFrame.AS_OF in frame.columns:
        dates = frame[BrokerPositionFrame.AS_OF].astype(str).str.strip()
        dates = dates[dates.ne("")]
        if not dates.empty:
            as_of = str(dates.max())
    currency = None
    if not frame.empty:
        currencies = frame[BrokerPositionFrame.CURRENCY].dropna().astype(str).str.strip()
        currencies = currencies[currencies.ne("")]
        if not currencies.empty:
            currency = currencies.iloc[0]
    total = (
        float(pd.to_numeric(frame[AssetsDef.VALUE], errors="coerce").fillna(0.0).sum())
        if not frame.empty
        else None
    )
    return RejestrLayer(
        frame=frame,
        n_positions=len(frame),
        total_value=total,
        value_currency=currency,
        as_of=as_of,
        warnings=warnings,
    )


def _degiro_view(as_of: date) -> RejestrAssetView:
    from app_proc.data_root import resolve_asset_dir
    from importers.degiro.data_model import DEFAULT_DEGIRO_ASSET_ID
    from importers.degiro.normalize import normalize_degiro_positions
    from importers.degiro.read_degiro import latest_portfolio_as_of, read_degiro_portfolio

    warnings: list[str] = []
    row, cat_warnings = _catalog_row(DEFAULT_DEGIRO_ASSET_ID)
    warnings.extend(cat_warnings)
    if row is None:
        return RejestrAssetView(
            asset=ASSET_DEGIRO,
            has_ruchy=False,
            stan=_broker_stan_from_positions(pd.DataFrame(), venue="degiro", warnings=warnings),
        )
    typ = str(row.get(AssetsDef.TYPE) or "").strip()
    asset_dir = resolve_asset_dir(DEFAULT_DEGIRO_ASSET_ID, typ)
    if not asset_dir.is_dir():
        warnings.append(f"Brak katalogu {asset_dir}.")
        return RejestrAssetView(
            asset=ASSET_DEGIRO,
            has_ruchy=False,
            stan=_broker_stan_from_positions(pd.DataFrame(), venue="degiro", warnings=warnings),
        )
    portfolio = latest_portfolio_as_of(
        read_degiro_portfolio(asset_dir, DEFAULT_DEGIRO_ASSET_ID), as_of
    )
    if portfolio.empty:
        warnings.append(f"Brak portfolio DEGIRO ≤ {as_of.isoformat()}.")
        positions = pd.DataFrame()
    else:
        positions = normalize_degiro_positions(portfolio, account_id=DEFAULT_DEGIRO_ASSET_ID)
    return RejestrAssetView(
        asset=ASSET_DEGIRO,
        has_ruchy=False,
        stan=_broker_stan_from_positions(positions, venue="degiro", warnings=warnings),
    )


def _xtb_view(as_of: date) -> RejestrAssetView:
    from app_proc.data_root import resolve_asset_dir
    from importers.xtb.data_model import DEFAULT_XTB_ASSET_ID
    from importers.xtb.normalize import normalize_xtb_positions
    from importers.xtb.read_xtb import latest_open_as_of, read_xtb_open

    warnings: list[str] = []
    row, cat_warnings = _catalog_row(DEFAULT_XTB_ASSET_ID)
    warnings.extend(cat_warnings)
    if row is None:
        return RejestrAssetView(
            asset=ASSET_XTB,
            has_ruchy=False,
            stan=_broker_stan_from_positions(pd.DataFrame(), venue="xtb", warnings=warnings),
        )
    typ = str(row.get(AssetsDef.TYPE) or "").strip()
    asset_dir = resolve_asset_dir(DEFAULT_XTB_ASSET_ID, typ)
    if not asset_dir.is_dir():
        warnings.append(f"Brak katalogu {asset_dir}.")
        return RejestrAssetView(
            asset=ASSET_XTB,
            has_ruchy=False,
            stan=_broker_stan_from_positions(pd.DataFrame(), venue="xtb", warnings=warnings),
        )
    latest = latest_open_as_of(read_xtb_open(asset_dir, DEFAULT_XTB_ASSET_ID), as_of)
    if latest.empty:
        warnings.append(f"Brak raportu XTB open ≤ {as_of.isoformat()}.")
        positions = pd.DataFrame()
    else:
        positions = normalize_xtb_positions(latest, account_id=DEFAULT_XTB_ASSET_ID)
    return RejestrAssetView(
        asset=ASSET_XTB,
        has_ruchy=False,
        stan=_broker_stan_from_positions(positions, venue="xtb", warnings=warnings),
    )


def _robo_view(as_of: date) -> RejestrAssetView:
    from app_proc.data_root import resolve_asset_dir
    from evaluators.evaluate_broker_revolut import (
        filter_trading_on_or_before,
        last_trade_prices,
        open_holdings_at_cost,
    )
    from importers.revolut.read_r_trading import read_revolut_trading_transactions
    from importers.revolut.trading_data_model import (
        DEFAULT_REVOLUT_ROBO_ASSET_ID,
        RevolutTradingFile,
    )

    warnings: list[str] = []
    cols = ["ticker", "qty", "avg_cost", "last_price", AssetsDef.VALUE, "currency"]
    row, cat_warnings = _catalog_row(DEFAULT_REVOLUT_ROBO_ASSET_ID)
    warnings.extend(cat_warnings)
    if row is None:
        return RejestrAssetView(
            asset=ASSET_ROBO,
            has_ruchy=False,
            stan=RejestrLayer(frame=pd.DataFrame(columns=cols), warnings=warnings),
        )
    typ = str(row.get(AssetsDef.TYPE) or "").strip()
    asset_dir = resolve_asset_dir(DEFAULT_REVOLUT_ROBO_ASSET_ID, typ)
    if not asset_dir.is_dir():
        warnings.append(f"Brak katalogu {asset_dir}.")
        return RejestrAssetView(
            asset=ASSET_ROBO,
            has_ruchy=False,
            stan=RejestrLayer(frame=pd.DataFrame(columns=cols), warnings=warnings),
        )

    trading_df, load_warnings = read_revolut_trading_transactions(
        asset_dir, DEFAULT_REVOLUT_ROBO_ASSET_ID
    )
    warnings.extend(load_warnings)
    trading_df = filter_trading_on_or_before(trading_df, as_of)
    if trading_df.empty:
        warnings.append(f"Brak transakcji Robo ≤ {as_of.isoformat()}.")
        return RejestrAssetView(
            asset=ASSET_ROBO,
            has_ruchy=False,
            stan=RejestrLayer(frame=pd.DataFrame(columns=cols), warnings=warnings),
        )

    holdings = open_holdings_at_cost(trading_df)
    prices = last_trade_prices(trading_df)
    eval_ts = pd.to_datetime(
        trading_df[RevolutTradingFile.DATE], format="ISO8601", utc=True
    ).max()
    eval_date = (
        str(eval_ts.date())
        if eval_ts is not None and not pd.isna(eval_ts)
        else as_of.isoformat()
    )
    catalog_currency = str(row.get(AssetsDef.CURRENCY) or "EUR").strip() or "EUR"

    rows = []
    for ticker, info in sorted(holdings.items()):
        qty = float(info.get("qty") or 0.0)
        if qty <= 1e-12:
            continue
        price = float(prices.get(ticker) or 0.0)
        cost = float(info.get("cost") or 0.0)
        avg_cost = (cost / qty) if qty else None
        value = qty * price if price > 0 else cost
        currency = str(info.get("currency") or catalog_currency).strip() or catalog_currency
        rows.append(
            {
                "ticker": ticker,
                "qty": qty,
                "avg_cost": avg_cost,
                "last_price": price if price > 0 else None,
                AssetsDef.VALUE: value,
                "currency": currency,
            }
        )
    frame = pd.DataFrame(rows, columns=cols)
    total = (
        float(pd.to_numeric(frame[AssetsDef.VALUE], errors="coerce").fillna(0.0).sum())
        if not frame.empty
        else None
    )
    currency = catalog_currency
    if not frame.empty:
        currencies = frame["currency"].dropna().astype(str).str.strip()
        if not currencies.empty:
            currency = currencies.iloc[0]
    return RejestrAssetView(
        asset=ASSET_ROBO,
        has_ruchy=False,
        stan=RejestrLayer(
            frame=frame,
            n_positions=len(frame),
            total_value=total,
            value_currency=currency,
            as_of=eval_date,
            warnings=warnings,
        ),
    )
