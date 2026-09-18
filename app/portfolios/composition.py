# -*- coding: utf-8 -*-
"""Skład portfela 3 G-MOMENTUM: pozycje instrumentów + gotówka brokerów."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from evaluators.broker_snapshot import BrokerHoldings
from importers.assets.data_model import AssetsDef
from importers.assets.instruments import InstrumentMap, InstrumentMapError, load_instrument_map
from importers.degiro.data_model import DEFAULT_DEGIRO_ASSET_ID, DegiroPortfolioFile
from importers.xtb.data_model import DEFAULT_XTB_ASSET_ID, XtbOpenPositionsFile
from portfolios.assignment import (
    PORTFOLIO_GM,
    PORTFOLIO_GM_ASSET_IDS,
    PORTFOLIO_GM_BROKER_ASSET_IDS,
    PORTFOLIO_GM_ORDER,
    gm_asset_role,
    nav_pln_for_portfolio,
)

_DISPLAY_NAMES = {
    DEFAULT_DEGIRO_ASSET_ID: "DEGIRO",
    DEFAULT_XTB_ASSET_ID: "XTB",
}

KIND_POSITION = "position"
KIND_CASH = "cash"


@dataclass(frozen=True)
class GmPositionLine:
    broker_id: str
    broker_label: str
    kind: str
    code: str
    label: str
    value: float
    currency: str
    evaluation_date: str = ""


def _component_label(asset_id: str) -> str:
    key = str(asset_id).strip()
    return _DISPLAY_NAMES.get(key, key)


def _cell(row: pd.Series | None, column: str, default: str = "") -> str:
    if row is None:
        return default
    value = row.get(column)
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    return str(value).strip()


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
    nav_pln: float,
    holdings: BrokerHoldings | None,
) -> tuple[float | None, float | None]:
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
    """Skład na poziomie konta brokera (DEGIRO / XTB)."""
    holdings_by_id = holdings_by_id or {}
    by_id = _rows_by_id(snapshot)
    total = nav_pln_for_portfolio(snapshot, PORTFOLIO_GM)
    rows: list[dict[str, object]] = []
    for asset_id in PORTFOLIO_GM_ORDER:
        snap_row = by_id.get(asset_id)
        nav_pln = _numeric(snap_row.get(AssetsDef.VALUE_PLN)) if snap_row is not None else 0.0
        native_value = _numeric(snap_row.get(AssetsDef.VALUE)) if snap_row is not None else 0.0
        currency = (
            str(snap_row.get(AssetsDef.CURRENCY) or "").strip()
            if snap_row is not None
            else ""
        )
        eval_date = _cell(snap_row, AssetsDef.EVALUATION_DATE)
        value_date = _cell(snap_row, AssetsDef.VALUE_DATE)
        days = None
        if snap_row is not None and AssetsDef.DAYS_AFTER_VALUATION in snap_row.index:
            days = pd.to_numeric(snap_row.get(AssetsDef.DAYS_AFTER_VALUATION), errors="coerce")
        in_snapshot = snap_row is not None
        positions_pln, cash_pln = _split_pln(
            nav_pln,
            holdings_by_id.get(asset_id),
        )
        weight = (nav_pln / total) if total else 0.0
        rows.append(
            {
                "id": asset_id,
                "Składnik": _component_label(asset_id),
                "Rola": gm_asset_role(asset_id),
                AssetsDef.VALUE: native_value,
                AssetsDef.CURRENCY: currency,
                AssetsDef.VALUE_PLN: nav_pln,
                AssetsDef.EVALUATION_DATE: eval_date,
                AssetsDef.VALUE_DATE: value_date,
                AssetsDef.DAYS_AFTER_VALUATION: days,
                "Udział": weight,
                "Pozycje PLN": positions_pln,
                "Gotówka PLN": cash_pln,
                "w_snapshocie": in_snapshot,
            }
        )
    return pd.DataFrame(rows)


def _soft_instrument_name(
    mapping: InstrumentMap | None,
    *,
    venue: str,
    code: str,
    fallback: str,
) -> str:
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


def _implied_fx_pln(snapshot: pd.DataFrame, broker_id: str, currency: str) -> float:
    """PLN za 1 jednostkę waluty pozycji — z wiersza brokera w snapshocie."""
    currency = str(currency or "").strip().upper()
    if not currency or currency == "PLN":
        return 1.0
    by_id = _rows_by_id(snapshot)
    row = by_id.get(broker_id)
    if row is None:
        return 1.0
    native = _numeric(row.get(AssetsDef.VALUE))
    pln = _numeric(row.get(AssetsDef.VALUE_PLN))
    if native == 0.0:
        return 1.0
    return pln / native


def compose_gm_instrument_composition(
    snapshot: pd.DataFrame,
    lines: list[GmPositionLine] | None = None,
) -> pd.DataFrame:
    """
    Skład per instrument (+ gotówka).

    Udział = wartość-pln / NAV portfela 3 G-MOMENTUM ze snapshota.
    Pozycje tego samego instrumentu z różnych kont są scalane.
    """
    lines = list(lines or [])
    total = nav_pln_for_portfolio(snapshot, PORTFOLIO_GM)
    buckets: dict[tuple[str, str], dict[str, object]] = {}

    for line in lines:
        fx = _implied_fx_pln(snapshot, line.broker_id, line.currency)
        value_pln = float(line.value) * fx
        if line.kind == KIND_CASH:
            key = (KIND_CASH, f"Gotówka ({line.broker_label})")
            label = f"Gotówka ({line.broker_label})"
            merge_brokers = False
        else:
            key = (KIND_POSITION, line.label)
            label = line.label
            merge_brokers = True

        bucket = buckets.get(key)
        if bucket is None:
            buckets[key] = {
                "kind": line.kind,
                "Składnik": label,
                "Konto": line.broker_label,
                "_brokers": {line.broker_label},
                AssetsDef.VALUE: float(line.value),
                AssetsDef.CURRENCY: line.currency,
                AssetsDef.VALUE_PLN: value_pln,
                AssetsDef.EVALUATION_DATE: line.evaluation_date,
            }
            continue

        bucket[AssetsDef.VALUE_PLN] = float(bucket[AssetsDef.VALUE_PLN]) + value_pln
        if merge_brokers:
            brokers: set[str] = bucket["_brokers"]  # type: ignore[assignment]
            brokers.add(line.broker_label)
            bucket["Konto"] = "+".join(sorted(brokers))
        prev_currency = str(bucket[AssetsDef.CURRENCY] or "")
        if prev_currency and line.currency and prev_currency != line.currency:
            bucket[AssetsDef.CURRENCY] = ""
            bucket[AssetsDef.VALUE] = float(bucket[AssetsDef.VALUE_PLN])
        elif prev_currency == line.currency:
            bucket[AssetsDef.VALUE] = float(bucket[AssetsDef.VALUE]) + float(line.value)
        else:
            bucket[AssetsDef.CURRENCY] = line.currency or prev_currency
            bucket[AssetsDef.VALUE] = float(bucket[AssetsDef.VALUE]) + float(line.value)
        if line.evaluation_date:
            prev_eval = str(bucket[AssetsDef.EVALUATION_DATE] or "")
            if not prev_eval or line.evaluation_date < prev_eval:
                bucket[AssetsDef.EVALUATION_DATE] = line.evaluation_date

    rows: list[dict[str, object]] = []
    for bucket in buckets.values():
        value_pln = float(bucket[AssetsDef.VALUE_PLN])
        rows.append(
            {
                "Składnik": bucket["Składnik"],
                "Konto": bucket["Konto"],
                AssetsDef.VALUE: bucket[AssetsDef.VALUE],
                AssetsDef.CURRENCY: bucket[AssetsDef.CURRENCY],
                AssetsDef.VALUE_PLN: value_pln,
                AssetsDef.EVALUATION_DATE: bucket[AssetsDef.EVALUATION_DATE],
                "Udział": (value_pln / total) if total else 0.0,
                "kind": bucket["kind"],
            }
        )

    empty_cols = [
        "Składnik",
        "Konto",
        AssetsDef.VALUE,
        AssetsDef.CURRENCY,
        AssetsDef.VALUE_PLN,
        AssetsDef.EVALUATION_DATE,
        "Udział",
        "kind",
    ]
    if not rows:
        return pd.DataFrame(columns=empty_cols)

    table = pd.DataFrame(rows)
    table["_sort_kind"] = table["kind"].map({KIND_POSITION: 0, KIND_CASH: 1}).fillna(2)
    table = table.sort_values(
        ["_sort_kind", AssetsDef.VALUE_PLN],
        ascending=[True, False],
    ).drop(columns=["_sort_kind"])
    return table.reset_index(drop=True)


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


def load_gm_position_lines(
    valuation_date: date,
    *,
    instruments: InstrumentMap | None = None,
) -> tuple[list[GmPositionLine], list[str]]:
    """Pozycje instrumentów + gotówka z DEGIRO/XTB na datę wyceny."""
    from app_proc.data_root import resolve_asset_dir
    from importers.assets.read_assets import read_assets
    from importers.degiro.read_degiro import latest_portfolio_as_of, read_degiro_portfolio
    from importers.xtb.read_xtb import (
        latest_open_as_of,
        read_xtb_open,
        resolve_xtb_cash_value,
        xtb_open_position_rows,
    )

    warnings: list[str] = []
    lines: list[GmPositionLine] = []

    mapping = instruments
    if mapping is None:
        try:
            mapping = load_instrument_map()
        except InstrumentMapError as exc:
            warnings.append(f"Brak mapowania instruments — nazwy z wyciągu: {exc}")
            mapping = None

    try:
        catalog = read_assets()
    except Exception as exc:
        return [], [f"Nie udało się wczytać katalogu do pozycji GM: {exc}"]

    if catalog.empty or AssetsDef.ID not in catalog.columns:
        return [], ["Brak katalogu aktywów do pozycji GM."]

    for broker_id in PORTFOLIO_GM_ORDER:
        broker_rows = catalog[catalog[AssetsDef.ID].astype(str).str.strip() == broker_id]
        if broker_rows.empty:
            warnings.append(f"Brak {broker_id} w katalogu — pominięte pozycje.")
            continue
        typ = str(broker_rows.iloc[0].get(AssetsDef.TYPE) or "").strip()
        asset_dir = resolve_asset_dir(broker_id, typ)
        label = _component_label(broker_id)

        if broker_id == DEFAULT_DEGIRO_ASSET_ID:
            if not asset_dir.is_dir():
                warnings.append(f"Brak katalogu {asset_dir} — bez pozycji DEGIRO.")
                continue
            portfolio = latest_portfolio_as_of(
                read_degiro_portfolio(asset_dir, broker_id), valuation_date
            )
            if portfolio.empty:
                warnings.append(f"Brak portfolio DEGIRO <= {valuation_date.isoformat()}.")
                continue
            eval_date = str(portfolio[DegiroPortfolioFile.PERIOD_END].max())
            isin_col = portfolio[DegiroPortfolioFile.ISIN]
            has_isin = isin_col.notna() & isin_col.astype(str).str.strip().ne("")
            positions = portfolio.loc[has_isin]
            cash = portfolio.loc[~has_isin]
            for isin, group in positions.groupby(
                positions[DegiroPortfolioFile.ISIN].astype(str).str.strip()
            ):
                value = float(
                    pd.to_numeric(group[DegiroPortfolioFile.VALUE_EUR], errors="coerce")
                    .fillna(0)
                    .sum()
                )
                product = str(group.iloc[0].get(DegiroPortfolioFile.PRODUCT) or "").strip()
                lines.append(
                    GmPositionLine(
                        broker_id=broker_id,
                        broker_label=label,
                        kind=KIND_POSITION,
                        code=isin,
                        label=_soft_instrument_name(
                            mapping, venue="degiro", code=isin, fallback=product or isin
                        ),
                        value=value,
                        currency="EUR",
                        evaluation_date=eval_date,
                    )
                )
            cash_value = (
                float(
                    pd.to_numeric(cash[DegiroPortfolioFile.VALUE_EUR], errors="coerce")
                    .fillna(0)
                    .sum()
                )
                if not cash.empty
                else 0.0
            )
            if abs(cash_value) > 1e-9:
                lines.append(
                    GmPositionLine(
                        broker_id=broker_id,
                        broker_label=label,
                        kind=KIND_CASH,
                        code="",
                        label=f"Gotówka ({label})",
                        value=cash_value,
                        currency="EUR",
                        evaluation_date=eval_date,
                    )
                )
            continue

        if broker_id == DEFAULT_XTB_ASSET_ID:
            if not asset_dir.is_dir():
                warnings.append(f"Brak katalogu {asset_dir} — bez pozycji XTB.")
                continue
            latest = latest_open_as_of(read_xtb_open(asset_dir, broker_id), valuation_date)
            if latest.empty:
                warnings.append(f"Brak raportu XTB open <= {valuation_date.isoformat()}.")
                continue
            eval_date = str(latest[XtbOpenPositionsFile.PERIOD_END].max())
            catalog_currency = str(broker_rows.iloc[0].get(AssetsDef.CURRENCY) or "PLN").strip()
            position_rows = xtb_open_position_rows(latest)
            if not position_rows.empty:
                for ticker, group in position_rows.groupby(
                    position_rows[XtbOpenPositionsFile.TICKER].astype(str).str.strip()
                ):
                    if not ticker:
                        continue
                    value = float(
                        pd.to_numeric(group[XtbOpenPositionsFile.VALUE], errors="coerce")
                        .fillna(0)
                        .sum()
                    )
                    product = str(group.iloc[0].get(XtbOpenPositionsFile.PRODUCT) or "").strip()
                    currency = str(group.iloc[0].get(XtbOpenPositionsFile.CURRENCY) or "").strip()
                    if not currency:
                        currency = catalog_currency or "PLN"
                    lines.append(
                        GmPositionLine(
                            broker_id=broker_id,
                            broker_label=label,
                            kind=KIND_POSITION,
                            code=ticker,
                            label=_soft_instrument_name(
                                mapping, venue="xtb", code=ticker, fallback=product or ticker
                            ),
                            value=value,
                            currency=currency,
                            evaluation_date=eval_date,
                        )
                    )
            cash_value, _n_cash = resolve_xtb_cash_value(latest, asset_dir, valuation_date)
            if abs(cash_value) > 1e-9:
                lines.append(
                    GmPositionLine(
                        broker_id=broker_id,
                        broker_label=label,
                        kind=KIND_CASH,
                        code="",
                        label=f"Gotówka ({label})",
                        value=cash_value,
                        currency=catalog_currency or "PLN",
                        evaluation_date=eval_date,
                    )
                )

    return lines, warnings
