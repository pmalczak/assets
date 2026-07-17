# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

from datetime import date

import pandas as pd

from importers.assets.data_model import (
    AssetsDef,
    AssetsFile,
    GoldCoinPurchaseRules,
    GoldCoinValuations,
    GroupDomain,
    KindDomain,
    TypeDomain,
)
from evaluators.valuation_date import filter_excel_rows_on_or_before, filter_on_or_before
from importers.assets.match_bank_transaction import (
    RuleMatchOutcome,
    match_purchase_rules,
    normalize_mbank_transactions,
    normalize_revolut_transactions,
)
from importers.mbank.data_model import MBankFile
from importers.revolut.account_data_model import RevolutAccountFile
from importers.assets.read_assets import read_gold_coin_purchase_rules, read_gold_coin_valuations
from importers.mbank.read_m_transactions import read_m_transactions
from importers.revolut.read_r_transactions import read_revolut_account_transactions


def evaluate_zloto_monety(
    data_root: Path,
    assets_file_row: pd.Series,
    assets_catalog: pd.DataFrame,
    valuation_date: date,
) -> tuple[pd.DataFrame, list[str]]:
    purchase_rules = read_gold_coin_purchase_rules()
    valuations = read_gold_coin_valuations()
    warnings: list[str] = []

    if purchase_rules.empty:
        warnings.append("Brak reguł zakupu w zakładce zloto-monety-zakupy.")
    else:
        GoldCoinPurchaseRules.check_structure(purchase_rules)

    outcomes = _match_all_purchase_rules(data_root, assets_catalog, purchase_rules, warnings, valuation_date)
    purchase_cost_pln = _sum_matched_purchases(outcomes, purchase_rules)

    if valuations.empty:
        warnings.append("Brak wycen w zakładce zloto-monety-wyceny.")
        evaluation_date = None
        value_pln = purchase_cost_pln
    else:
        GoldCoinValuations.check_structure(valuations)
        valuations = filter_excel_rows_on_or_before(valuations, GoldCoinValuations.DATE, valuation_date)
        if valuations.empty:
            warnings.append(f"Brak wyceny zlota-monety na date {valuation_date}.")
            evaluation_date = None
            value_pln = purchase_cost_pln
        else:
            latest = valuations.sort_values(GoldCoinValuations.DATE, ascending=False).iloc[0]
            evaluation_date = pd.Timestamp(latest[GoldCoinValuations.DATE]).strftime("%Y-%m-%d")
            value_pln = float(latest[GoldCoinValuations.VALUE])

    assets_row = AssetsDef.as_assets_row(assets_file_row)
    assets_row[AssetsDef.GROUP] = GroupDomain.GOLD_COINS
    assets_row[AssetsDef.TYPE] = TypeDomain.GOLD_COINS
    assets_row[AssetsDef.VALUE] = value_pln
    assets_row[AssetsDef.EVALUATION_DATE] = evaluation_date
    assets_row[AssetsDef.DESCR] = _build_description(outcomes, purchase_rules)

    result = pd.DataFrame([assets_row])
    AssetsDef.check_structure(result)
    return result, warnings


def _match_all_purchase_rules(
    data_root: Path,
    assets_catalog: pd.DataFrame,
    purchase_rules: pd.DataFrame,
    warnings: list[str],
    valuation_date: date,
) -> list[RuleMatchOutcome]:
    if purchase_rules.empty:
        return []

    catalog = assets_catalog.set_index(AssetsFile.ID, drop=False)
    outcomes: list[RuleMatchOutcome] = []

    for source_account, rules in purchase_rules.groupby(GoldCoinPurchaseRules.SOURCE_ACCOUNT):
        source_account = str(source_account)
        if source_account not in catalog.index:
            warnings.append(f"Nieznane konto źródłowe {source_account!r} w regułach zakupu monet.")
            continue

        source_row = catalog.loc[source_account]
        if isinstance(source_row, pd.DataFrame):
            source_row = source_row.iloc[0]

        transactions = _load_source_transactions(data_root, source_row, valuation_date)
        account_outcomes = match_purchase_rules(rules, transactions)
        for outcome in account_outcomes:
            if outcome.message:
                warnings.append(outcome.message)
        outcomes.extend(account_outcomes)

    return outcomes


def _load_source_transactions(data_root: Path, source_row: pd.Series, valuation_date: date) -> pd.DataFrame:
    source_id = str(source_row[AssetsFile.ID])
    kind = str(source_row[AssetsFile.KIND])

    if kind.startswith(KindDomain.MBANK):
        raw = read_m_transactions(data_root, source_id)
        raw = filter_on_or_before(raw, MBankFile.MBANK_TRANSACTION_DATE, valuation_date)
        return normalize_mbank_transactions(raw)

    if kind.startswith(KindDomain.REVOLUT):
        raw = read_revolut_account_transactions(data_root / source_id, source_id)
        raw = filter_on_or_before(raw, RevolutAccountFile.DATE, valuation_date)
        return normalize_revolut_transactions(raw)

    raise ValueError(f"Nieobslugiwane konto zrodlowe {source_id!r} ({kind}).")


def _sum_matched_purchases(
    outcomes: list[RuleMatchOutcome],
    purchase_rules: pd.DataFrame,
) -> float:
    total = 0.0

    for outcome in outcomes:
        if outcome.status != "ok":
            continue
        amount = float(outcome.matches.iloc[0]["amount"])
        total += abs(amount)

    return total


def _build_description(outcomes: list[RuleMatchOutcome], purchase_rules: pd.DataFrame) -> str:
    ok_count = sum(1 for outcome in outcomes if outcome.status == "ok")
    total_rules = len(purchase_rules)
    return f"dopasowane zakupy: {ok_count}/{total_rules}"
