# -*- coding: utf-8 -*-
"""Pomiar niesparowanych przepływów funding cash-pool ↔ venue (scenariusz B).

Σ per korytarz; bez korekty NAV. Soft reconcile Robo/XTB Adyen zostają w ROI —
tu wspólny raport strukturalny (+ DEGIRO/XTB Revolut+mBank, Trade Republic, savings).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from analyse_assets.account_tx import AccountTx
from analyse_assets.accounts_pools import load_accounts_pool
from app_proc.data_root import resolve_asset_dir
from evaluators.evaluate_broker_revolut import (
    filter_trading_on_or_before,
    parse_trading_number,
)
from evaluators.valuation_date import filter_excel_rows_on_or_before, filter_on_or_before
from importers.assets.data_model import AssetsDef, TypeDomain
from importers.assets.pool_id import MBANK_PLN, REVOLUT_EUR, REVOLUT_PLN
from importers.assets.read_assets import read_assets
from importers.degiro.data_model import DEFAULT_DEGIRO_ASSET_ID, DegiroAccountFile
from importers.degiro.read_degiro import parse_degiro_date, read_degiro_account
from importers.revolut.deposit_data_model import RevolutDepositFile
from importers.revolut.read_r_deposits import read_revolut_deposit_transactions
from importers.revolut.savings_statement import OPIS_DEPOSIT, OPIS_WITHDRAWAL
from importers.revolut.trading_data_model import RevolutTradingFile
from importers.traderepublic.data_model import (
    DEFAULT_TRADEREPUBLIC_ASSET_ID,
    TradeRepublicFile,
)
from importers.traderepublic.read_traderepublic import read_traderepublic_transactions
from importers.xtb.data_model import (
    CASH_OP_DEPOSIT,
    DEFAULT_XTB_ASSET_ID,
    DEFAULT_XTB_CLIENT_ID,
    XtbCashOperationsFile,
    classify_xtb_cash_type,
)
from importers.xtb.read_xtb import parse_xtb_date, read_xtb_cash
from roi.broker_trading_roi import (
    DEFAULT_BROKER_ASSET_ID,
    TO_ROBO_TITLE,
    _load_broker_trading,
)
from roi.revolut_deposit_roi import DEPOSIT_ASSET_IDS
from roi.xtb_roi import RECONCILE_TOLERANCE_PLN, _filter_xtb_rows_on_or_before

RECONCILE_TOLERANCE_EUR = 0.01
TO_DEGIRO_TITLE = "To Stichting DEGIRO"
MBANK_DEGIRO_COUNTERPARTY = r"stichting\s*degiro"
DEGIRO_DEPOSIT_DESCRIPTION = "Depozyt"
_TRADE_REPUBLIC_TITLE = r"trade\s*republic"
_REVOLUT_XTB_TITLE = r"\bxtb\b"
_XTB_CARD_DEPOSIT_COMMENT = "adyen"
_XTB_PEKAO_COMMENT = "pekao"
_MBANK_XTB_COUNTERPARTY = r"xtb\s+sp[oó][lł]ka"
_MBANK_XTB_TITLE = rf"\b{DEFAULT_XTB_CLIENT_ID}\b"
TITLE_DEPOSITING_SAVINGS = "Depositing savings"
TITLE_WITHDRAWING_SAVINGS = "Withdrawing savings"

STATUS_OK = "ok"
STATUS_MISMATCH = "mismatch"
STATUS_B_ONLY = "b_only"
STATUS_ERROR = "error"

# Max |data_A − data_B| przy sparowaniu po kwocie (opóźnienie rozliczenia).
MATCH_SETTLEMENT_DAYS = 7

MATCH_KIND_EXACT = "exact"
MATCH_KIND_SETTLEMENT = "settlement"
MATCH_KIND_A_ONLY = "a_only"
MATCH_KIND_B_ONLY = "b_only"

MATCHED_LEG_COLUMNS = [
    "date_a",
    "amount_a",
    "date_b",
    "amount_b",
    "date_skew_days",
    "match",
]


def _side(asset_id: str, description: str) -> str:
    """Etykieta strony korytarza: ``{id aktywa}: {opis transakcji}``."""
    return f"{asset_id}: {description}"

REPORT_COLUMNS = [
    "corridor",
    "currency",
    "side_a",
    "amount_a",
    "tx_a",
    "side_b",
    "amount_b",
    "tx_b",
    "diff",
    "status",
    "detail",
]


@dataclass(frozen=True)
class FlowLeg:
    date: str
    amount: float


@dataclass(frozen=True)
class CorridorRow:
    corridor: str
    currency: str
    side_a: str
    amount_a: float
    side_b: str
    amount_b: float
    status: str
    detail: str = ""
    tx_a: str = ""
    tx_b: str = ""

    @property
    def diff(self) -> float:
        return abs(self.amount_b) - abs(self.amount_a)

    def as_dict(self) -> dict:
        return {
            "corridor": self.corridor,
            "currency": self.currency,
            "side_a": self.side_a,
            "amount_a": round(float(self.amount_a), 2),
            "tx_a": self.tx_a,
            "side_b": self.side_b,
            "amount_b": round(float(self.amount_b), 2),
            "tx_b": self.tx_b,
            "diff": round(float(self.diff), 2),
            "status": self.status,
            "detail": self.detail,
        }


def build_funding_report(
    valuation_date: date,
    *,
    revolut_eur_pool: pd.DataFrame | None = None,
    revolut_pln_pool: pd.DataFrame | None = None,
    mbank_pln_pool: pd.DataFrame | None = None,
    robo_trading: pd.DataFrame | None = None,
    degiro_account: pd.DataFrame | None = None,
    xtb_cash: pd.DataFrame | None = None,
    traderepublic: pd.DataFrame | None = None,
    savings_by_account: dict[str, pd.DataFrame] | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Raport Σ funding per korytarz ≤ data wyceny.

    Ramki opcjonalne (testy); ``None`` → odczyt z dysku / pool.
    Kolumny ``tx_a`` / ``tx_b``: ``YYYY-MM-DD: kwota`` (lista legów do odszukania na wyciągu).
    """
    warnings: list[str] = []
    rows: list[CorridorRow] = []

    eur_pool, eur_err = _resolve_pool(revolut_eur_pool, REVOLUT_EUR)
    if eur_err:
        warnings.append(eur_err)
    pln_pool, pln_err = _resolve_pool(revolut_pln_pool, REVOLUT_PLN)
    if pln_err:
        warnings.append(pln_err)
    mbank_pool, mbank_err = _resolve_pool(mbank_pln_pool, MBANK_PLN)
    if mbank_err:
        warnings.append(mbank_err)

    rows.append(_corridor_robo(valuation_date, eur_pool, robo_trading, warnings))
    rows.extend(
        _corridors_degiro(
            valuation_date,
            eur_pool,
            mbank_pool,
            degiro_account,
            warnings,
        )
    )
    rows.extend(
        _corridors_xtb(valuation_date, pln_pool, mbank_pool, xtb_cash, warnings)
    )
    rows.append(_corridor_traderepublic(valuation_date, pln_pool, traderepublic, warnings))
    rows.extend(
        _corridors_savings(valuation_date, eur_pool, pln_pool, savings_by_account, warnings)
    )

    frame = pd.DataFrame([r.as_dict() for r in rows], columns=REPORT_COLUMNS)
    for msg in frame.loc[frame["status"] == STATUS_MISMATCH, "detail"].tolist():
        if msg and msg not in warnings:
            warnings.append(msg)
    return frame, warnings


def format_flow_legs(legs: list[FlowLeg]) -> str:
    if not legs:
        return ""
    ordered = sorted(legs, key=lambda leg: (leg.date, leg.amount))
    return "; ".join(f"{leg.date}: {leg.amount:.2f}" for leg in ordered)


def parse_flow_legs(tx: str) -> list[FlowLeg]:
    """Odwrotność ``format_flow_legs`` — ``YYYY-MM-DD: kwota`` rozdzielone ``;``."""
    legs: list[FlowLeg] = []
    for part in str(tx or "").split(";"):
        part = part.strip()
        if not part or ":" not in part:
            continue
        date_s, amount_s = part.split(":", 1)
        date_s = date_s.strip()
        amount = pd.to_numeric(amount_s.strip(), errors="coerce")
        if not date_s or pd.isna(amount):
            continue
        legs.append(FlowLeg(date_s, float(amount)))
    return legs


@dataclass(frozen=True)
class MatchedLegPair:
    date_a: str | None
    amount_a: float | None
    date_b: str | None
    amount_b: float | None
    match: str

    @property
    def date_skew_days(self) -> int | None:
        if not self.date_a or not self.date_b:
            return None
        return abs(
            (date.fromisoformat(self.date_a) - date.fromisoformat(self.date_b)).days
        )

    def as_dict(self) -> dict:
        return {
            "date_a": self.date_a or "",
            "amount_a": None if self.amount_a is None else round(float(self.amount_a), 2),
            "date_b": self.date_b or "",
            "amount_b": None if self.amount_b is None else round(float(self.amount_b), 2),
            "date_skew_days": self.date_skew_days,
            "match": self.match,
        }


def match_flow_legs(
    legs_a: list[FlowLeg],
    legs_b: list[FlowLeg],
    *,
    amount_tolerance: float = 0.01,
    max_date_skew_days: int = MATCH_SETTLEMENT_DAYS,
) -> list[MatchedLegPair]:
    """Paruje legi A↔B: najpierw data+kwota, potem kwota z tolerancją daty rozliczenia."""
    a_list = list(legs_a)
    b_list = list(legs_b)
    used_a: set[int] = set()
    used_b: set[int] = set()
    pairs: list[tuple[int, int, str]] = []

    def _amount_ok(la: FlowLeg, lb: FlowLeg) -> bool:
        return abs(float(la.amount) - float(lb.amount)) <= amount_tolerance

    def _skew(la: FlowLeg, lb: FlowLeg) -> int:
        return abs(
            (date.fromisoformat(la.date) - date.fromisoformat(lb.date)).days
        )

    # Faza 1: ta sama data + kwota.
    for i, la in enumerate(a_list):
        for j, lb in enumerate(b_list):
            if j in used_b:
                continue
            if la.date == lb.date and _amount_ok(la, lb):
                used_a.add(i)
                used_b.add(j)
                pairs.append((i, j, MATCH_KIND_EXACT))
                break

    # Faza 2: kwota + najbliższa data ≤ max_date_skew_days.
    for i, la in enumerate(a_list):
        if i in used_a:
            continue
        best_j: int | None = None
        best_key: tuple[int, float, int] | None = None
        for j, lb in enumerate(b_list):
            if j in used_b or not _amount_ok(la, lb):
                continue
            skew = _skew(la, lb)
            if skew > max_date_skew_days:
                continue
            key = (skew, abs(float(la.amount) - float(lb.amount)), j)
            if best_key is None or key < best_key:
                best_j, best_key = j, key
        if best_j is not None:
            used_a.add(i)
            used_b.add(best_j)
            pairs.append((i, best_j, MATCH_KIND_SETTLEMENT))

    rows: list[MatchedLegPair] = []
    for i, j, kind in pairs:
        la, lb = a_list[i], b_list[j]
        rows.append(
            MatchedLegPair(
                date_a=la.date,
                amount_a=la.amount,
                date_b=lb.date,
                amount_b=lb.amount,
                match=kind,
            )
        )
    for i, la in enumerate(a_list):
        if i in used_a:
            continue
        rows.append(
            MatchedLegPair(
                date_a=la.date,
                amount_a=la.amount,
                date_b=None,
                amount_b=None,
                match=MATCH_KIND_A_ONLY,
            )
        )
    for j, lb in enumerate(b_list):
        if j in used_b:
            continue
        rows.append(
            MatchedLegPair(
                date_a=None,
                amount_a=None,
                date_b=lb.date,
                amount_b=lb.amount,
                match=MATCH_KIND_B_ONLY,
            )
        )

    def _sort_key(row: MatchedLegPair) -> tuple[str, str, float]:
        d = row.date_a or row.date_b or ""
        other = row.date_b or row.date_a or ""
        amt = float(row.amount_a if row.amount_a is not None else row.amount_b or 0.0)
        return (d, other, amt)

    return sorted(rows, key=_sort_key)


def matched_legs_frame(
    tx_a: str,
    tx_b: str,
    *,
    amount_tolerance: float = 0.01,
    max_date_skew_days: int = MATCH_SETTLEMENT_DAYS,
) -> pd.DataFrame:
    """Ramka sparowanych legów z ``tx_a`` / ``tx_b`` (format ``format_flow_legs``)."""
    pairs = match_flow_legs(
        parse_flow_legs(tx_a),
        parse_flow_legs(tx_b),
        amount_tolerance=amount_tolerance,
        max_date_skew_days=max_date_skew_days,
    )
    if not pairs:
        return pd.DataFrame(columns=MATCHED_LEG_COLUMNS)
    return pd.DataFrame([p.as_dict() for p in pairs], columns=MATCHED_LEG_COLUMNS)


def _resolve_pool(
    provided: pd.DataFrame | None, pool_id: str
) -> tuple[pd.DataFrame, str | None]:
    if provided is not None:
        return provided, None
    try:
        return load_accounts_pool(pool_id), None
    except Exception as exc:  # noqa: BLE001 — raport: warning zamiast crash
        return pd.DataFrame(), f"Nie udało się wczytać {pool_id}: {exc}"


def _match_status(
    amount_a: float,
    amount_b: float,
    *,
    tolerance: float,
    corridor: str,
    currency: str,
    side_a: str,
    side_b: str,
) -> tuple[str, str]:
    diff = abs(amount_b) - abs(amount_a)
    if abs(diff) <= tolerance:
        if abs(amount_a) <= 1e-9 and abs(amount_b) <= 1e-9:
            return STATUS_OK, "brak przepływów"
        return STATUS_OK, ""
    detail = (
        f"{corridor} funding mismatch: {side_a}={abs(amount_a):.2f} {currency} vs "
        f"{side_b}={abs(amount_b):.2f} {currency} (diff={diff:.2f} {currency})"
    )
    return STATUS_MISMATCH, detail


def _corridor_from_legs(
    *,
    corridor_id: str,
    corridor_label: str,
    currency: str,
    side_a: str,
    legs_a: list[FlowLeg],
    side_b: str,
    legs_b: list[FlowLeg],
    tolerance: float,
) -> CorridorRow:
    amount_a = sum(leg.amount for leg in legs_a)
    amount_b = sum(leg.amount for leg in legs_b)
    status, detail = _match_status(
        amount_a,
        amount_b,
        tolerance=tolerance,
        corridor=corridor_label,
        currency=currency,
        side_a=side_a,
        side_b=side_b,
    )
    return CorridorRow(
        corridor=corridor_id,
        currency=currency,
        side_a=side_a,
        amount_a=amount_a,
        side_b=side_b,
        amount_b=amount_b,
        status=status,
        detail=detail,
        tx_a=format_flow_legs(legs_a),
        tx_b=format_flow_legs(legs_b),
    )


def _corridor_robo(
    valuation_date: date,
    eur_pool: pd.DataFrame,
    trading_df: pd.DataFrame | None,
    warnings: list[str],
) -> CorridorRow:
    side_a = _side(REVOLUT_EUR, "|To Robo portfolio|")
    side_b = _side(DEFAULT_BROKER_ASSET_ID, "CASH TOP-UP")
    try:
        if trading_df is None:
            trading_df = _load_robo_trading()
        legs_a = _legs_pool_title(eur_pool, TO_ROBO_TITLE, valuation_date)
        legs_b = _legs_cash_top_up(trading_df, valuation_date)
    except Exception as exc:  # noqa: BLE001
        msg = f"Robo: nie udało się policzyć funding: {exc}"
        warnings.append(msg)
        return CorridorRow(
            "robo", "EUR", side_a, 0.0, side_b, 0.0, STATUS_ERROR, msg
        )
    return _corridor_from_legs(
        corridor_id="robo",
        corridor_label="Robo",
        currency="EUR",
        side_a=side_a,
        legs_a=legs_a,
        side_b=side_b,
        legs_b=legs_b,
        tolerance=RECONCILE_TOLERANCE_EUR,
    )


def _corridors_degiro(
    valuation_date: date,
    eur_pool: pd.DataFrame,
    mbank_pln_pool: pd.DataFrame,
    account_df: pd.DataFrame | None,
    warnings: list[str],
) -> list[CorridorRow]:
    """Dwa źródła funding: Revolut EUR oraz mBank PLN (osobne waluty Depozyt)."""
    side_a_revolut = _side(REVOLUT_EUR, "|To Stichting DEGIRO|")
    side_a_mbank = _side(MBANK_PLN, "|STICHTING DEGIRO|")
    side_b_eur = _side(DEFAULT_DEGIRO_ASSET_ID, "Depozyt EUR")
    side_b_pln = _side(DEFAULT_DEGIRO_ASSET_ID, "Depozyt PLN")
    try:
        if account_df is None:
            account_df = _load_degiro_account()
        legs_revolut = _legs_pool_title(eur_pool, TO_DEGIRO_TITLE, valuation_date)
        legs_mbank = _legs_pool_counterparty(
            mbank_pln_pool, MBANK_DEGIRO_COUNTERPARTY, valuation_date
        )
        legs_eur = _legs_degiro_deposits(account_df, valuation_date, currency="EUR")
        legs_pln = _legs_degiro_deposits(account_df, valuation_date, currency="PLN")
    except Exception as exc:  # noqa: BLE001
        msg = f"DEGIRO: nie udało się policzyć funding: {exc}"
        warnings.append(msg)
        return [
            CorridorRow(
                "degiro_revolut",
                "EUR",
                side_a_revolut,
                0.0,
                side_b_eur,
                0.0,
                STATUS_ERROR,
                msg,
            )
        ]

    return [
        _corridor_from_legs(
            corridor_id="degiro_revolut",
            corridor_label="DEGIRO Revolut",
            currency="EUR",
            side_a=side_a_revolut,
            legs_a=legs_revolut,
            side_b=side_b_eur,
            legs_b=legs_eur,
            tolerance=RECONCILE_TOLERANCE_EUR,
        ),
        _corridor_from_legs(
            corridor_id="degiro_mbank",
            corridor_label="DEGIRO mBank",
            currency="PLN",
            side_a=side_a_mbank,
            legs_a=legs_mbank,
            side_b=side_b_pln,
            legs_b=legs_pln,
            tolerance=RECONCILE_TOLERANCE_PLN,
        ),
    ]


def _corridors_xtb(
    valuation_date: date,
    revolut_pln_pool: pd.DataFrame,
    mbank_pln_pool: pd.DataFrame,
    cash_df: pd.DataFrame | None,
    warnings: list[str],
) -> list[CorridorRow]:
    """Dwa źródła: karta Revolut (Adyen) oraz przelew mBank (Comment~Pekao na XTB)."""
    side_a_revolut = _side(REVOLUT_PLN, "|Revolut XTB|")
    side_b_adyen = _side(DEFAULT_XTB_ASSET_ID, "Adyen Deposit")
    side_a_mbank = _side(MBANK_PLN, f"|XTB {DEFAULT_XTB_CLIENT_ID}|")
    side_b_pekao = _side(DEFAULT_XTB_ASSET_ID, "Pekao Deposit")
    try:
        if cash_df is None:
            cash_df = _load_xtb_cash(warnings)
        legs_revolut = _legs_pool_title(
            revolut_pln_pool, _REVOLUT_XTB_TITLE, valuation_date, regex=True
        )
        legs_mbank = _legs_mbank_xtb(mbank_pln_pool, valuation_date)
        legs_adyen = _legs_xtb_deposits(
            cash_df, valuation_date, comment_needle=_XTB_CARD_DEPOSIT_COMMENT
        )
        legs_pekao = _legs_xtb_deposits(
            cash_df, valuation_date, comment_needle=_XTB_PEKAO_COMMENT
        )
    except Exception as exc:  # noqa: BLE001
        msg = f"XTB: nie udało się policzyć funding: {exc}"
        warnings.append(msg)
        return [
            CorridorRow(
                "xtb_adyen",
                "PLN",
                side_a_revolut,
                0.0,
                side_b_adyen,
                0.0,
                STATUS_ERROR,
                msg,
            )
        ]

    return [
        _corridor_from_legs(
            corridor_id="xtb_adyen",
            corridor_label="XTB Adyen",
            currency="PLN",
            side_a=side_a_revolut,
            legs_a=legs_revolut,
            side_b=side_b_adyen,
            legs_b=legs_adyen,
            tolerance=RECONCILE_TOLERANCE_PLN,
        ),
        _corridor_from_legs(
            corridor_id="xtb_mbank",
            corridor_label="XTB mBank",
            currency="PLN",
            side_a=side_a_mbank,
            legs_a=legs_mbank,
            side_b=side_b_pekao,
            legs_b=legs_pekao,
            tolerance=RECONCILE_TOLERANCE_PLN,
        ),
    ]


def _corridor_traderepublic(
    valuation_date: date,
    pln_pool: pd.DataFrame,
    blotter: pd.DataFrame | None,
    warnings: list[str],
) -> CorridorRow:
    side_a = _side(REVOLUT_PLN, "|Trade Republic| (karta)")
    side_b = _side(DEFAULT_TRADEREPUBLIC_ASSET_ID, "CUSTOMER_INPAYMENT")
    try:
        if blotter is None:
            blotter = _load_traderepublic()
        legs_a = _legs_pool_title(
            pln_pool, _TRADE_REPUBLIC_TITLE, valuation_date, regex=True
        )
        legs_b = _legs_traderepublic_inpayments(blotter, valuation_date)
    except Exception as exc:  # noqa: BLE001
        msg = f"Trade Republic: nie udało się policzyć funding: {exc}"
        warnings.append(msg)
        return CorridorRow(
            "traderepublic", "PLN", side_a, 0.0, side_b, 0.0, STATUS_ERROR, msg
        )
    return _corridor_from_legs(
        corridor_id="traderepublic",
        corridor_label="Trade Republic",
        currency="PLN",
        side_a=side_a,
        legs_a=legs_a,
        side_b=side_b,
        legs_b=legs_b,
        tolerance=RECONCILE_TOLERANCE_PLN,
    )


def _corridors_savings(
    valuation_date: date,
    eur_pool: pd.DataFrame,
    pln_pool: pd.DataFrame,
    savings_by_account: dict[str, pd.DataFrame] | None,
    warnings: list[str],
) -> list[CorridorRow]:
    rows: list[CorridorRow] = []
    for account_id in DEPOSIT_ASSET_IDS:
        currency = "EUR" if account_id.endswith("_eur") else "PLN"
        pool = eur_pool if currency == "EUR" else pln_pool
        tol = RECONCILE_TOLERANCE_EUR if currency == "EUR" else RECONCILE_TOLERANCE_PLN
        corridor_deposit = f"savings_deposit:{account_id}"
        pool_id = REVOLUT_EUR if currency == "EUR" else REVOLUT_PLN
        side_a_deposit = _side(pool_id, "Depositing savings")
        side_b_deposit = _side(account_id, "Depozyt")
        side_a_withdraw = _side(pool_id, "Withdrawing savings")
        side_b_withdraw = _side(account_id, "Wypłata")
        try:
            dep_df = _resolve_savings(account_id, savings_by_account)
            legs_depositing = _legs_pool_title(
                pool,
                TITLE_DEPOSITING_SAVINGS,
                valuation_date,
                account_id=account_id,
            )
            legs_withdrawing = _legs_pool_title(
                pool,
                TITLE_WITHDRAWING_SAVINGS,
                valuation_date,
                account_id=account_id,
            )
            legs_depozyt = _legs_savings_opis(dep_df, OPIS_DEPOSIT, valuation_date)
            legs_wyplata = _legs_savings_opis(dep_df, OPIS_WITHDRAWAL, valuation_date)
        except Exception as exc:  # noqa: BLE001
            msg = f"Savings {account_id}: {exc}"
            warnings.append(msg)
            rows.append(
                CorridorRow(
                    corridor_deposit,
                    currency,
                    side_a_deposit,
                    0.0,
                    side_b_deposit,
                    0.0,
                    STATUS_ERROR,
                    msg,
                )
            )
            continue

        rows.append(
            _corridor_from_legs(
                corridor_id=corridor_deposit,
                corridor_label=f"Savings deposit {account_id}",
                currency=currency,
                side_a=side_a_deposit,
                legs_a=legs_depositing,
                side_b=side_b_deposit,
                legs_b=legs_depozyt,
                tolerance=tol,
            )
        )
        if legs_withdrawing or legs_wyplata:
            rows.append(
                _corridor_from_legs(
                    corridor_id=f"savings_withdraw:{account_id}",
                    corridor_label=f"Savings withdraw {account_id}",
                    currency=currency,
                    side_a=side_a_withdraw,
                    legs_a=legs_withdrawing,
                    side_b=side_b_withdraw,
                    legs_b=legs_wyplata,
                    tolerance=tol,
                )
            )
    return rows


def _legs_pool_title(
    pool_tx: pd.DataFrame,
    title: str,
    valuation_date: date | None,
    *,
    regex: bool = False,
    account_id: str | None = None,
) -> list[FlowLeg]:
    if pool_tx is None or pool_tx.empty:
        return []
    if AccountTx.TITLE not in pool_tx.columns or AccountTx.AMOUNT not in pool_tx.columns:
        return []
    df = pool_tx
    if account_id is not None and AccountTx.ACCOUNT_ID in df.columns:
        df = df[df[AccountTx.ACCOUNT_ID].astype(str) == account_id]
    if valuation_date is not None and AccountTx.TRANSACTION_DATE in df.columns:
        df = filter_excel_rows_on_or_before(df, AccountTx.TRANSACTION_DATE, valuation_date)
    mask = df[AccountTx.TITLE].astype(str).str.contains(
        title, case=False, na=False, regex=regex
    )
    legs: list[FlowLeg] = []
    for _, row in df.loc[mask].iterrows():
        amount = pd.to_numeric(pd.Series([row[AccountTx.AMOUNT]]), errors="coerce").iloc[0]
        if pd.isna(amount) or abs(float(amount)) <= 1e-12:
            continue
        date_s = _iso_date(row.get(AccountTx.TRANSACTION_DATE))
        if not date_s:
            continue
        legs.append(FlowLeg(date_s, abs(float(amount))))
    return legs


def _legs_cash_top_up(
    trading_df: pd.DataFrame, valuation_date: date | None
) -> list[FlowLeg]:
    if trading_df is None or trading_df.empty:
        return []
    df = trading_df
    if valuation_date is not None:
        df = filter_trading_on_or_before(df, valuation_date)
    mask = df[RevolutTradingFile.TYPE] == RevolutTradingFile.TYPE_CASH_TOP_UP
    legs: list[FlowLeg] = []
    for _, row in df.loc[mask].iterrows():
        amount = parse_trading_number(row[RevolutTradingFile.TOTAL_AMOUNT])
        if amount is None or abs(float(amount)) <= 1e-12:
            continue
        date_s = _iso_date(row.get(RevolutTradingFile.DATE))
        if not date_s:
            continue
        legs.append(FlowLeg(date_s, abs(float(amount))))
    return legs


def _legs_pool_counterparty(
    pool_tx: pd.DataFrame,
    counterparty_pattern: str,
    valuation_date: date | None,
) -> list[FlowLeg]:
    if pool_tx is None or pool_tx.empty:
        return []
    if (
        AccountTx.COUNTERPARTY not in pool_tx.columns
        or AccountTx.AMOUNT not in pool_tx.columns
    ):
        return []
    df = pool_tx
    if valuation_date is not None and AccountTx.TRANSACTION_DATE in df.columns:
        df = filter_excel_rows_on_or_before(df, AccountTx.TRANSACTION_DATE, valuation_date)
    mask = df[AccountTx.COUNTERPARTY].astype(str).str.contains(
        counterparty_pattern, case=False, na=False, regex=True
    )
    return _legs_from_pool_mask(df, mask)


def _legs_mbank_xtb(
    pool_tx: pd.DataFrame, valuation_date: date | None
) -> list[FlowLeg]:
    """Przelewy mBank → XTB: kontrahent XTB S.A. albo tytuł = nr rachunku klienta."""
    if pool_tx is None or pool_tx.empty or AccountTx.AMOUNT not in pool_tx.columns:
        return []
    df = pool_tx
    if valuation_date is not None and AccountTx.TRANSACTION_DATE in df.columns:
        df = filter_excel_rows_on_or_before(df, AccountTx.TRANSACTION_DATE, valuation_date)
    cp = (
        df[AccountTx.COUNTERPARTY].astype(str)
        if AccountTx.COUNTERPARTY in df.columns
        else pd.Series("", index=df.index)
    )
    title = (
        df[AccountTx.TITLE].astype(str)
        if AccountTx.TITLE in df.columns
        else pd.Series("", index=df.index)
    )
    mask = cp.str.contains(_MBANK_XTB_COUNTERPARTY, case=False, na=False, regex=True)
    mask = mask | title.str.contains(_MBANK_XTB_TITLE, case=False, na=False, regex=True)
    return _legs_from_pool_mask(df, mask)


def _legs_from_pool_mask(df: pd.DataFrame, mask: pd.Series) -> list[FlowLeg]:
    legs: list[FlowLeg] = []
    for _, row in df.loc[mask].iterrows():
        amount = pd.to_numeric(pd.Series([row[AccountTx.AMOUNT]]), errors="coerce").iloc[0]
        if pd.isna(amount) or abs(float(amount)) <= 1e-12:
            continue
        date_s = _iso_date(row.get(AccountTx.TRANSACTION_DATE))
        if not date_s:
            continue
        legs.append(FlowLeg(date_s, abs(float(amount))))
    return legs


def _legs_degiro_deposits(
    account_df: pd.DataFrame,
    valuation_date: date | None,
    *,
    currency: str,
) -> list[FlowLeg]:
    if account_df is None or account_df.empty:
        return []
    df = account_df
    if valuation_date is not None and DegiroAccountFile.BOOKING_DATE in df.columns:
        work = df.copy()
        work["_iso"] = work[DegiroAccountFile.BOOKING_DATE].map(
            lambda v: parse_degiro_date(v).isoformat()
        )
        cutoff = valuation_date.isoformat()
        df = work.loc[work["_iso"] <= cutoff]
    if df.empty:
        return []
    desc = df[DegiroAccountFile.DESCRIPTION].astype(str).str.strip()
    mask = desc.str.casefold() == DEGIRO_DEPOSIT_DESCRIPTION.casefold()
    want = currency.strip().upper()
    if DegiroAccountFile.CHANGE_CURRENCY in df.columns:
        cur = df[DegiroAccountFile.CHANGE_CURRENCY].astype(str).str.strip().str.upper()
        # Brak waluty: tylko do korytarza EUR (historyczne wiersze testowe bez kolumny).
        currency_ok = cur.eq(want) | ((want == "EUR") & cur.isin({"", "NAN"}))
        mask = mask & currency_ok
    elif want != "EUR":
        return []
    legs: list[FlowLeg] = []
    for _, row in df.loc[mask].iterrows():
        change = pd.to_numeric(pd.Series([row[DegiroAccountFile.CHANGE]]), errors="coerce").iloc[0]
        if pd.isna(change) or float(change) <= 1e-12:
            continue
        if "_iso" in row.index and pd.notna(row["_iso"]):
            date_s = str(row["_iso"])
        else:
            date_s = parse_degiro_date(row[DegiroAccountFile.BOOKING_DATE]).isoformat()
        legs.append(FlowLeg(date_s, abs(float(change))))
    return legs


def _legs_traderepublic_inpayments(
    blotter: pd.DataFrame, valuation_date: date | None
) -> list[FlowLeg]:
    if blotter is None or blotter.empty:
        return []
    df = blotter
    if valuation_date is not None and TradeRepublicFile.DATE in df.columns:
        df = filter_on_or_before(df, TradeRepublicFile.DATE, valuation_date)
    mask = (
        df[TradeRepublicFile.TYPE].astype(str).str.strip()
        == TradeRepublicFile.TYPE_CUSTOMER_INPAYMENT
    )
    legs: list[FlowLeg] = []
    for _, row in df.loc[mask].iterrows():
        amount = pd.to_numeric(pd.Series([row[TradeRepublicFile.AMOUNT]]), errors="coerce").iloc[0]
        if pd.isna(amount) or abs(float(amount)) <= 1e-12:
            continue
        date_s = _iso_date(row.get(TradeRepublicFile.DATE))
        if not date_s:
            continue
        legs.append(FlowLeg(date_s, abs(float(amount))))
    return legs


def _legs_xtb_deposits(
    cash_operations_df: pd.DataFrame,
    valuation_date: date | None,
    *,
    comment_needle: str,
) -> list[FlowLeg]:
    if cash_operations_df is None or cash_operations_df.empty:
        return []
    df = cash_operations_df
    if valuation_date is not None and XtbCashOperationsFile.TIME in df.columns:
        df = _filter_xtb_rows_on_or_before(df, XtbCashOperationsFile.TIME, valuation_date)
    if df.empty or XtbCashOperationsFile.TYPE not in df.columns:
        return []
    type_ok = df[XtbCashOperationsFile.TYPE].map(classify_xtb_cash_type) == CASH_OP_DEPOSIT
    comment = (
        df[XtbCashOperationsFile.COMMENT].astype(str)
        if XtbCashOperationsFile.COMMENT in df.columns
        else pd.Series("", index=df.index)
    )
    needle = comment.str.contains(comment_needle, case=False, na=False)
    legs: list[FlowLeg] = []
    for _, row in df.loc[type_ok & needle].iterrows():
        amount = pd.to_numeric(
            pd.Series([row[XtbCashOperationsFile.AMOUNT]]), errors="coerce"
        ).iloc[0]
        if pd.isna(amount) or abs(float(amount)) <= 1e-12:
            continue
        parsed = parse_xtb_date(row.get(XtbCashOperationsFile.TIME))
        if parsed is None:
            continue
        legs.append(FlowLeg(parsed.isoformat(), abs(float(amount))))
    return legs


def _legs_savings_opis(
    deposit_df: pd.DataFrame, opis: str, valuation_date: date | None
) -> list[FlowLeg]:
    if deposit_df is None or deposit_df.empty:
        return []
    df = deposit_df
    if valuation_date is not None and RevolutDepositFile.DATE in df.columns:
        df = filter_on_or_before(df, RevolutDepositFile.DATE, valuation_date)
    mask = df[RevolutDepositFile.DESCRIPTION].astype(str).str.strip() == opis
    col = RevolutDepositFile.MONEY_IN if opis == OPIS_DEPOSIT else RevolutDepositFile.MONEY_OUT
    if col not in df.columns:
        return []
    legs: list[FlowLeg] = []
    for _, row in df.loc[mask].iterrows():
        amount = pd.to_numeric(pd.Series([row[col]]), errors="coerce").iloc[0]
        if pd.isna(amount) or abs(float(amount)) <= 1e-12:
            continue
        date_s = _iso_date(row.get(RevolutDepositFile.DATE))
        if not date_s:
            continue
        legs.append(FlowLeg(date_s, abs(float(amount))))
    return legs


def _iso_date(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, date) and not isinstance(value, pd.Timestamp):
        return value.isoformat()
    ts = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(ts):
        ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return None
    if getattr(ts, "tzinfo", None) is not None:
        ts = ts.tz_convert(None)
    return ts.date().isoformat()


def _resolve_savings(
    account_id: str, savings_by_account: dict[str, pd.DataFrame] | None
) -> pd.DataFrame:
    if savings_by_account is not None and account_id in savings_by_account:
        return savings_by_account[account_id]
    asset_dir = resolve_asset_dir(account_id, TypeDomain.CURRENT_ACCOUNT)
    if not Path(asset_dir).is_dir():
        return pd.DataFrame()
    return read_revolut_deposit_transactions(asset_dir, account_id)


def _load_robo_trading() -> pd.DataFrame:
    trading_df, _load_warnings = _load_broker_trading(DEFAULT_BROKER_ASSET_ID)
    return trading_df


def _load_degiro_account() -> pd.DataFrame:
    asset_dir = _broker_dir(DEFAULT_DEGIRO_ASSET_ID)
    df, _warnings = read_degiro_account(asset_dir, DEFAULT_DEGIRO_ASSET_ID)
    return df


def _load_xtb_cash(warnings: list[str]) -> pd.DataFrame:
    asset_dir = _broker_dir(DEFAULT_XTB_ASSET_ID)
    df, cash_warnings = read_xtb_cash(asset_dir, DEFAULT_XTB_ASSET_ID)
    warnings.extend(cash_warnings)
    return df


def _load_traderepublic() -> pd.DataFrame:
    asset_dir = _broker_dir(DEFAULT_TRADEREPUBLIC_ASSET_ID)
    return read_traderepublic_transactions(asset_dir, DEFAULT_TRADEREPUBLIC_ASSET_ID)


def _broker_dir(broker_id: str) -> Path:
    from roi.asset_dir import require_broker_asset_dir

    return require_broker_asset_dir(broker_id)


__all__ = [
    "MATCHED_LEG_COLUMNS",
    "MATCH_KIND_A_ONLY",
    "MATCH_KIND_B_ONLY",
    "MATCH_KIND_EXACT",
    "MATCH_KIND_SETTLEMENT",
    "MATCH_SETTLEMENT_DAYS",
    "MatchedLegPair",
    "REPORT_COLUMNS",
    "STATUS_B_ONLY",
    "STATUS_ERROR",
    "STATUS_MISMATCH",
    "STATUS_OK",
    "TO_DEGIRO_TITLE",
    "TO_ROBO_TITLE",
    "build_funding_report",
    "format_flow_legs",
    "match_flow_legs",
    "matched_legs_frame",
    "parse_flow_legs",
]
