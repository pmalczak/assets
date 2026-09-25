from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from importers.assets.data_model import PurchaseRules, TitleMatchDomain


@dataclass(frozen=True)
class RuleMatchOutcome:
    rule_id: str
    status: str
    matches: pd.DataFrame
    message: str


def match_purchase_rules(
    rules: pd.DataFrame,
    transactions: pd.DataFrame,
) -> list[RuleMatchOutcome]:
    PurchaseRules.check_structure(rules)
    normalized = transactions.copy()
    outcomes: list[RuleMatchOutcome] = []

    for _, rule in rules.iterrows():
        rule_id = str(rule[PurchaseRules.RULE_ID])
        matched = _apply_rule(rule, normalized)
        count = len(matched)

        if count == 0:
            outcomes.append(
                RuleMatchOutcome(
                    rule_id=rule_id,
                    status="no_match",
                    matches=matched,
                    message=f"Brak dopasowania dla reguly {rule_id!r}.",
                )
            )
        elif count == 1:
            outcomes.append(
                RuleMatchOutcome(
                    rule_id=rule_id,
                    status="ok",
                    matches=matched,
                    message="",
                )
            )
        else:
            outcomes.append(
                RuleMatchOutcome(
                    rule_id=rule_id,
                    status="multiple_matches",
                    matches=matched,
                    message=(
                        f"Regula {rule_id!r} dopasowala {count} transakcji; "
                        "oczekiwano dokladnie jednej."
                    ),
                )
            )

    return outcomes


def _apply_rule(rule: pd.Series, transactions: pd.DataFrame) -> pd.DataFrame:
    matched = transactions.copy()
    if matched.empty:
        return matched

    exact_date = rule.get(PurchaseRules.DATE)
    if pd.notna(exact_date):
        target = pd.Timestamp(exact_date).normalize()
        matched = matched[matched["date"].dt.normalize() == target]

    date_from = rule.get(PurchaseRules.DATE_FROM)
    if pd.notna(date_from):
        matched = matched[matched["date"] >= pd.Timestamp(date_from).normalize()]

    date_to = rule.get(PurchaseRules.DATE_TO)
    if pd.notna(date_to):
        matched = matched[matched["date"] <= pd.Timestamp(date_to).normalize()]

    title = rule.get(PurchaseRules.TITLE)
    if pd.notna(title) and str(title).strip():
        matched = matched[_match_title(matched["title"], str(title), rule)]

    counterparty = rule.get(PurchaseRules.COUNTERPARTY)
    if pd.notna(counterparty) and str(counterparty).strip():
        needle = str(counterparty).casefold()
        matched = matched[matched["counterparty"].str.casefold().str.contains(needle, regex=False, na=False)]

    counterparty_account = rule.get(PurchaseRules.COUNTERPARTY_IBAN)
    if pd.notna(counterparty_account) and str(counterparty_account).strip():
        expected = _normalize_account(str(counterparty_account))
        matched = matched[
            matched["counterparty_account"].map(_normalize_account) == expected
        ]

    amount = rule.get(PurchaseRules.AMOUNT)
    if pd.notna(amount):
        tolerance = rule.get(PurchaseRules.AMOUNT_TOLERANCE)
        tolerance = 0.0 if pd.isna(tolerance) else float(tolerance)
        expected = float(amount)
        matched = matched[(matched["amount"] - expected).abs() <= tolerance]

    operation_description = rule.get(PurchaseRules.OPERATION_DESCRIPTION)
    if pd.notna(operation_description) and str(operation_description).strip():
        expected = str(operation_description).casefold()
        matched = matched[matched["operation_description"].str.casefold() == expected]

    return matched.reset_index(drop=True)


def _match_title(series: pd.Series, expected: str, rule: pd.Series) -> pd.Series:
    mode = rule.get(PurchaseRules.TITLE_MATCH)
    if pd.isna(mode) or not str(mode).strip():
        mode = TitleMatchDomain.CONTAINS
    mode = str(mode).strip().lower()

    if mode == TitleMatchDomain.EXACT:
        return series.str.casefold() == expected.casefold()
    if mode == TitleMatchDomain.REGEX:
        pattern = re.compile(expected, flags=re.IGNORECASE)
        return series.fillna("").map(lambda value: bool(pattern.search(str(value))))
    return series.str.casefold().str.contains(expected.casefold(), regex=False, na=False)


def _normalize_account(value: str) -> str:
    return "".join(ch for ch in value.upper() if ch.isalnum())
