from __future__ import annotations

from pathlib import Path

import pandas as pd

from app_proc.data_root import get_online_data_root
from importers.assets.data_model import AssetsDef, GroupDomain, KindDomain, Properties
from importers.assets.property_lifecycle import (
    load_property_close_dates,
    property_valuation_history,
)
from importers.assets.read_assets import get_assets_file, read_property_valuations
from roi.config import read_analyse_config
from importers.mbank.data_model import MBankFile
from importers.mbank.read_m_transactions import read_m_transactions
from importers.pkobp.data_model import PkoBpBonds
from importers.revolut.read_r_deposits import read_revolut_deposit_transactions
from importers.revolut.read_r_transactions import read_revolut_account_transactions
from importers.revolut.account_data_model import RevolutAccountFile
from importers.revolut.deposit_data_model import RevolutDepositFile
from evaluators.evaluate_obigacjeskarbowe import read_obligacje
from nbp_fx_repo.nbp_fx_repository import NBP_API_EUR


def build_portfolio_history(
    assets_catalog: pd.DataFrame,
    fx_rates: pd.DataFrame,
    end_date: pd.Timestamp | None = None,
    days: int = 365,
) -> dict[str, object]:
    if end_date is None:
        end_date = pd.Timestamp.today().normalize()
    else:
        end_date = pd.Timestamp(end_date).normalize()

    start_date = end_date - pd.Timedelta(days=days - 1)
    data_root = get_online_data_root()

    history_points: list[pd.DataFrame] = []
    supported_assets: list[str] = []
    skipped_assets: list[str] = []

    for _, asset_row in assets_catalog.iterrows():
        kind = asset_row.get(AssetsDef.KIND)
        asset_id = str(asset_row.get(AssetsDef.ID, "unknown"))

        if pd.isna(kind):
            skipped_assets.append(f"{asset_id}: missing kind")
            continue

        try:
            series = _build_asset_history(data_root, asset_row)
        except Exception as exc:
            skipped_assets.append(f"{asset_id}: {kind} ({exc})")
            continue

        if series.empty:
            skipped_assets.append(f"{asset_id}: {kind} (no history rows)")
            continue

        history_points.append(series)
        supported_assets.append(f"{asset_id}: {kind}")

    if not history_points:
        return {
            "history": pd.DataFrame(columns=["date", "group", "value_pln"]),
            "supported_assets": supported_assets,
            "skipped_assets": skipped_assets,
            "start_date": start_date,
            "end_date": end_date,
        }

    raw_history = pd.concat(history_points, ignore_index=True)
    daily_asset_values = _daily_asset_values(raw_history, start_date, end_date)
    eur_fx = _daily_eur_fx(fx_rates, start_date, end_date)

    history = daily_asset_values.merge(eur_fx, on="date", how="left")
    history["fx"] = history["currency"].where(history["currency"] == "PLN", history["eur_fx"])
    history["fx"] = history["fx"].replace({"PLN": 1.0}).astype(float)
    history["value_pln"] = history["value"] * history["fx"]

    portfolio = (
        history.groupby(["date", "group"], as_index=False)["value_pln"]
        .sum()
        .sort_values(["date", "group"])
    )

    return {
        "history": portfolio,
        "supported_assets": supported_assets,
        "skipped_assets": skipped_assets,
        "start_date": start_date,
        "end_date": end_date,
    }


def _build_asset_history(data_root: Path, asset_row: pd.Series) -> pd.DataFrame:
    kind = str(asset_row[AssetsDef.KIND])

    if kind.startswith(KindDomain.MBANK):
        return _mbank_history(data_root, asset_row)
    if kind.startswith(KindDomain.REVOLUT):
        return _revolut_history(data_root, asset_row)
    if kind == KindDomain.BONDS:
        return _bonds_history(data_root, asset_row)
    if kind.startswith(f"{KindDomain.ASSETS}."):
        return _assets_sheet_history(asset_row)
    return pd.DataFrame(columns=["asset_key", "group", "date", "value", "currency"])


def _mbank_history(data_root: Path, asset_row: pd.Series) -> pd.DataFrame:
    asset_id = str(asset_row[AssetsDef.ID])
    currency = str(asset_row[AssetsDef.CURRENCY]).upper()

    df = read_m_transactions(data_root, asset_id)
    if df.empty:
        return pd.DataFrame(columns=["asset_key", "group", "date", "value", "currency"])

    history = (
        df[[MBankFile.MBANK_TRANSACTION_DATE, MBankFile.MBANK_OUTSTANDING_BALANCE]]
        .rename(
            columns={
                MBankFile.MBANK_TRANSACTION_DATE: "date",
                MBankFile.MBANK_OUTSTANDING_BALANCE: "value",
            }
        )
        .copy()
    )
    history["date"] = pd.to_datetime(history["date"])
    history["value"] = pd.to_numeric(history["value"], errors="coerce")
    history = history.dropna(subset=["date", "value"])
    history = history.groupby("date", as_index=False)["value"].last()
    history["asset_key"] = asset_id
    history["group"] = str(asset_row[AssetsDef.GROUP])
    history["currency"] = currency
    return history[["asset_key", "group", "date", "value", "currency"]]


def _revolut_history(data_root: Path, asset_row: pd.Series) -> pd.DataFrame:
    asset_id = str(asset_row[AssetsDef.ID])
    input_path = data_root / asset_id
    currency = str(asset_row[AssetsDef.CURRENCY]).upper()

    series_parts: list[pd.DataFrame] = []
    group_name = str(asset_row[AssetsDef.GROUP])

    df_accounts = read_revolut_account_transactions(input_path, asset_id)
    if not df_accounts.empty:
        accounts = (
            df_accounts[[RevolutAccountFile.DATE, RevolutAccountFile.BALANCE]]
            .rename(columns={RevolutAccountFile.DATE: "date", RevolutAccountFile.BALANCE: "value"})
            .copy()
        )
        accounts["date"] = pd.to_datetime(accounts["date"])
        accounts["value"] = pd.to_numeric(accounts["value"], errors="coerce")
        accounts = accounts.dropna(subset=["date", "value"])
        accounts = accounts.groupby("date", as_index=False)["value"].last()
        accounts["asset_key"] = f"{asset_id}:account"
        accounts["group"] = group_name
        accounts["currency"] = currency
        series_parts.append(accounts[["asset_key", "group", "date", "value", "currency"]])

    df_deposits = read_revolut_deposit_transactions(input_path, asset_id)
    if not df_deposits.empty:
        deposits = (
            df_deposits[[RevolutDepositFile.DATE, RevolutDepositFile.BALANCE, RevolutDepositFile.CURRENCY]]
            .rename(
                columns={
                    RevolutDepositFile.DATE: "date",
                    RevolutDepositFile.BALANCE: "value",
                    RevolutDepositFile.CURRENCY: "currency",
                }
            )
            .copy()
        )
        deposits["date"] = pd.to_datetime(deposits["date"])
        deposits["value"] = pd.to_numeric(deposits["value"], errors="coerce")
        deposits["currency"] = deposits["currency"].astype(str).str.upper()
        deposits = deposits.dropna(subset=["date", "value"])
        deposits = deposits.groupby("date", as_index=False).last()
        deposits["asset_key"] = f"{asset_id}:deposit"
        deposits["group"] = GroupDomain.DEPOSIT
        series_parts.append(deposits[["asset_key", "group", "date", "value", "currency"]])

    if not series_parts:
        return pd.DataFrame(columns=["asset_key", "group", "date", "value", "currency"])

    return pd.concat(series_parts, ignore_index=True)


def _bonds_history(data_root: Path, asset_row: pd.Series) -> pd.DataFrame:
    asset_id = str(asset_row[AssetsDef.ID])
    currency = str(asset_row[AssetsDef.CURRENCY]).upper()
    input_path = data_root / asset_id

    df = read_obligacje(input_path, asset_id)
    if df.empty:
        return pd.DataFrame(columns=["asset_key", "group", "date", "value", "currency"])

    history = (
        df[[PkoBpBonds.DATE, PkoBpBonds.AMOUNT]]
        .rename(columns={PkoBpBonds.DATE: "date", PkoBpBonds.AMOUNT: "value"})
        .copy()
    )
    history["date"] = pd.to_datetime(history["date"])
    history["value"] = pd.to_numeric(history["value"], errors="coerce")
    history = history.dropna(subset=["date", "value"])
    history = history.groupby("date", as_index=False)["value"].sum()
    history["value"] = history["value"].cumsum()
    history["asset_key"] = asset_id
    history["group"] = str(asset_row[AssetsDef.GROUP])
    history["currency"] = currency
    return history[["asset_key", "group", "date", "value", "currency"]]


def _assets_sheet_history(asset_row: pd.Series) -> pd.DataFrame:
    kind = str(asset_row[AssetsDef.KIND])
    sheet_name = kind.split(".", 1)[1]
    sheet = pd.read_excel(get_assets_file(), sheet_name=sheet_name)

    if kind.startswith("assets.IKE-") or kind == "assets.rocky-iv":
        return _single_series_history(
            sheet=sheet,
            asset_key=str(asset_row[AssetsDef.ID]),
            group_name=str(asset_row[AssetsDef.GROUP]),
            currency=str(asset_row[AssetsDef.CURRENCY]).upper(),
        )

    if kind == "assets.cash":
        result: list[pd.DataFrame] = []
        for currency, group in sheet.groupby("waluta"):
            history = _single_series_history(
                sheet=group,
                asset_key=f"{asset_row[AssetsDef.ID]}:{str(currency).upper()}",
                group_name=str(asset_row[AssetsDef.GROUP]),
                currency=str(currency).upper(),
            )
            if not history.empty:
                result.append(history)
        if result:
            return pd.concat(result, ignore_index=True)
        return pd.DataFrame(columns=["asset_key", "group", "date", "value", "currency"])

    if kind in ("assets.properties-wyceny", "assets.properties"):
        valuations = read_property_valuations()
        config = read_analyse_config()
        close_dates = load_property_close_dates(config["manual"], config["catalog"])
        result = []
        for property_id in sorted(valuations[Properties.ID].astype(str).unique()):
            history = property_valuation_history(valuations, property_id, close_dates)
            if history.empty:
                continue
            history["asset_key"] = f"{asset_row[AssetsDef.ID]}:{property_id}"
            history["group"] = str(asset_row[AssetsDef.GROUP])
            history["currency"] = history["currency"].astype(str).str.upper()
            result.append(history[["asset_key", "group", "date", "value", "currency"]])

        if result:
            return pd.concat(result, ignore_index=True)
        return pd.DataFrame(columns=["asset_key", "group", "date", "value", "currency"])

    return pd.DataFrame(columns=["asset_key", "group", "date", "value", "currency"])


def _single_series_history(sheet: pd.DataFrame, asset_key: str, group_name: str, currency: str) -> pd.DataFrame:
    date_column = "Data"
    value_column = AssetsDef.VALUE
    if date_column not in sheet.columns or value_column not in sheet.columns:
        return pd.DataFrame(columns=["asset_key", "group", "date", "value", "currency"])

    history = sheet[[date_column, value_column]].copy()
    history["date"] = pd.to_datetime(history[date_column])
    history["value"] = pd.to_numeric(history[value_column], errors="coerce")
    history = history.dropna(subset=["date", "value"])
    history = history.groupby("date", as_index=False)["value"].last()
    history["asset_key"] = asset_key
    history["group"] = group_name
    history["currency"] = currency
    return history[["asset_key", "group", "date", "value", "currency"]]


def _daily_asset_values(raw_history: pd.DataFrame, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
    index = pd.date_range(start_date, end_date, freq="D")
    result: list[pd.DataFrame] = []

    for asset_key, group in raw_history.groupby("asset_key"):
        group = group.sort_values("date").copy()
        series = group.set_index("date")["value"]
        series = series[~series.index.duplicated(keep="last")]
        series = series.reindex(series.index.union(index)).sort_index().ffill()
        series = series.reindex(index).fillna(0.0)

        asset_daily = pd.DataFrame(
            {
                "date": index,
                "asset_key": asset_key,
                "group": group["group"].iloc[-1],
                "currency": group["currency"].iloc[-1],
                "value": series.values,
            }
        )
        result.append(asset_daily)

    return pd.concat(result, ignore_index=True)


def _daily_eur_fx(fx_rates: pd.DataFrame, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
    fx = fx_rates.copy().reset_index()
    date_column = fx.columns[0]
    fx = fx[[date_column, NBP_API_EUR]].rename(columns={date_column: "date", NBP_API_EUR: "eur_fx"})
    fx["date"] = pd.to_datetime(fx["date"])

    index = pd.date_range(start_date, end_date, freq="D")
    fx = (
        fx.groupby("date", as_index=False)["eur_fx"]
        .last()
        .set_index("date")
        .reindex(index)
        .ffill()
        .bfill()
        .reset_index()
        .rename(columns={"index": "date"})
    )
    return fx
