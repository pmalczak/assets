# -*- coding: utf-8 -*-
"""
Walidacja analyse_assets_config.xlsx względem schematu i rzeczywistych procedur.

Akceptuje wyłącznie nową strukturę (AccountTx / pool_id).
Aliasy wsteczne (MBANK_*, SOURCE, kolumna ``source``) są błędami.
"""
from __future__ import annotations

__author__ = "pmalczak@gmail.com"

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import pandas as pd

from analyse_assets.build_selector import (
    MAPPING_MAP,
    is_blank_rule_value,
    rule_cell_str,
)
from analyse_assets.accounts_pools import load_accounts_pool
from analyse_assets.build_selector import build_step_selector, get_mapping
from analyse_assets.select_asset import select_asset
from analyse_assets.config_model import CATALOG_SHEET, CATEGORY_NAMES, DEFAULT_POOL_ID
from analyse_assets.config_model import MANUAL_SHEET, MANUAL_TRANSACTION_SOURCE
from analyse_assets.config_model import MAPPING_NAMES, OPERATOR_NAMES
from analyse_assets.config_model import RULES_SHEET
from analyse_assets.config_model import AnalyseAssetsCatalog, AnalyseAssetsManual, AnalyseAssetsRules
from analyse_assets.account_tx import AccountTx
from analyse_assets.data_model import AssetRw
from importers.assets.pool_id import POOL_IDS, MBANK_PLN
from roi.config import get_config_file, read_analyse_config

Severity = Literal["error", "warning"]

# Kanoniczne kody pól w kolumnie rules.field (bez aliasów).
CANONICAL_FIELDS = frozenset({
    "OPERATION_TYPE",
    "TITLE",
    "COUNTERPARTY",
    "ACCOUNT_NUMBER",
    "AMOUNT",
    "ACCOUNT_ID",
    "POOL_ID",
    "YEAR",
})

# Stare kody → nowe (wsteczna kompatybilność = błąd walidatora).
LEGACY_FIELD_ALIASES: dict[str, str] = {
    "MBANK_DESCRIPTION": "OPERATION_TYPE",
    "MBANK_TITLE": "TITLE",
    "MBANK_TRANSACTION_PARTY": "COUNTERPARTY",
    "MBANK_ACCOUNT_NUMBER": "ACCOUNT_NUMBER",
    "MBANK_AMOUNT": "AMOUNT",
    "MBANK_SOURCE_ACCOUNT": "ACCOUNT_ID",
    "SOURCE": "POOL_ID",
}

LEGACY_COLUMN_NAME = "source"  # Excel: source → pool_id

# pool_id obsługiwane przez walidator / alokację.
SUPPORTED_TRANSACTION_SOURCES = frozenset(POOL_IDS)
SUPPORTED_POOL_IDS = SUPPORTED_TRANSACTION_SOURCES

# Pola reguł dozwolone dla danego pool_id.
FIELDS_BY_SOURCE: dict[str, frozenset[str]] = {
    pool_id: CANONICAL_FIELDS for pool_id in POOL_IDS
}

# Operatory sensowne dla pola (zgodne z apply_condition).
OPERATORS_BY_FIELD: dict[str, frozenset[str]] = {
    "TITLE": frozenset({"contains", "contains_no_regex", "equals"}),
    "COUNTERPARTY": frozenset({"contains", "contains_no_regex", "equals"}),
    "OPERATION_TYPE": frozenset({"contains", "contains_no_regex", "equals"}),
    "ACCOUNT_NUMBER": frozenset({"contains", "contains_no_regex", "equals"}),
    "ACCOUNT_ID": frozenset({"contains", "contains_no_regex", "equals"}),
    "AMOUNT": frozenset({"equals", "gt", "gte", "lte", "lt"}),
    "POOL_ID": frozenset({"equals", "contains", "contains_no_regex"}),
    "YEAR": frozenset({"equals", "gte", "gt", "lte", "lt"}),
}

_NEGATIVE_MANUAL_CATEGORIES = frozenset({"INVESTMENT", "OUTFLOW"})
_POSITIVE_MANUAL_CATEGORIES = frozenset({"INFLOW", "CLOSING"})


@dataclass(frozen=True)
class ValidationIssue:
    severity: Severity
    sheet: str
    location: str
    code: str
    message: str

    def format(self) -> str:
        return f"[{self.severity}] {self.sheet} | {self.location} | {self.code}: {self.message}"


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)
    config_path: Path | None = None

    def add(
        self,
        severity: Severity,
        sheet: str,
        location: str,
        code: str,
        message: str,
    ) -> None:
        self.issues.append(
            ValidationIssue(severity, sheet, location, code, message)
        )

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors


def _loc_asset(asset_id) -> str:
    return f"asset_id={asset_id!r}"


def _loc_rule(asset_id, step_id, row_idx) -> str:
    return f"asset_id={asset_id!r} step_id={step_id!r} row={row_idx}"


def _loc_manual(asset_id, row_idx) -> str:
    return f"asset_id={asset_id!r} row={row_idx}"


def _catalog_source(row: pd.Series) -> str:
    if AnalyseAssetsCatalog.POOL_ID not in row.index or is_blank_rule_value(
        row[AnalyseAssetsCatalog.POOL_ID]
    ):
        return DEFAULT_POOL_ID
    return str(row[AnalyseAssetsCatalog.POOL_ID]).strip()


def _step_effective_source(step_rules: pd.DataFrame, default_source: str) -> str:
    from roi.allocate import _effective_rule_pool_id

    return _effective_rule_pool_id(step_rules, default_source)


def _read_raw_rules(config_path: Path) -> pd.DataFrame:
    return pd.read_excel(config_path, sheet_name=RULES_SHEET)


def _validate_raw_sheet_columns(
    config_path: Path,
    sheet: str,
    *,
    required_pool_id: bool,
    report: ValidationReport,
) -> pd.DataFrame | None:
    """Sprawdza surowy Excel: kolumna ``source`` = błąd; wymagany ``pool_id``."""
    try:
        df = pd.read_excel(config_path, sheet_name=sheet)
    except Exception as exc:  # noqa: BLE001
        report.add(
            "error",
            sheet,
            "-",
            "sheet_unread",
            f"Nie udało się odczytać arkusza: {exc}",
        )
        return None

    columns = {str(c) for c in df.columns}
    if LEGACY_COLUMN_NAME in columns:
        report.add(
            "error",
            sheet,
            "columns",
            "legacy_column",
            f"Kolumna {LEGACY_COLUMN_NAME!r} jest aliasem wstecznym — "
            f"przemianuj na {AnalyseAssetsCatalog.POOL_ID!r}",
        )
    if required_pool_id and AnalyseAssetsCatalog.POOL_ID not in columns:
        report.add(
            "error",
            sheet,
            "columns",
            "missing_pool_id_column",
            f"Brak kolumny {AnalyseAssetsCatalog.POOL_ID!r}",
        )
    return df


def _validate_raw_schema(config_path: Path, report: ValidationReport) -> None:
    _validate_raw_sheet_columns(
        config_path, CATALOG_SHEET, required_pool_id=True, report=report
    )
    raw_rules = _validate_raw_sheet_columns(
        config_path, RULES_SHEET, required_pool_id=True, report=report
    )
    if raw_rules is not None:
        _validate_raw_incomplete_rules(raw_rules, report)


def _validate_catalog(catalog: pd.DataFrame, report: ValidationReport) -> set[str]:
    asset_ids: list[str] = []
    for idx, row in catalog.iterrows():
        asset_id = row.get(AnalyseAssetsCatalog.ASSET_ID)
        loc = f"row={idx}"
        if is_blank_rule_value(asset_id):
            report.add("error", CATALOG_SHEET, loc, "blank_asset_id", "Puste asset_id")
            continue
        asset_id = str(asset_id).strip()
        loc = _loc_asset(asset_id)
        asset_ids.append(asset_id)

        if is_blank_rule_value(row.get(AnalyseAssetsCatalog.OUTPUT_FILE)):
            report.add(
                "error",
                CATALOG_SHEET,
                loc,
                "blank_output_file",
                "Puste output_file",
            )

        try:
            int(row[AnalyseAssetsCatalog.ORDER])
        except (TypeError, ValueError):
            report.add(
                "error",
                CATALOG_SHEET,
                loc,
                "bad_order",
                f"order musi być liczbą całkowitą, jest {row[AnalyseAssetsCatalog.ORDER]!r}",
            )

        source = _catalog_source(row)
        if source == MANUAL_TRANSACTION_SOURCE:
            report.add(
                "error",
                CATALOG_SHEET,
                loc,
                "invalid_catalog_source",
                f"pool_id={source!r} jest zarezerwowane dla wierszy manual",
            )
        elif source not in SUPPORTED_POOL_IDS:
            report.add(
                "error",
                CATALOG_SHEET,
                loc,
                "unsupported_source",
                f"pool_id={source!r} nie jest obsługiwane "
                f"(dozwolone: {sorted(SUPPORTED_POOL_IDS)})",
            )

    duplicates = {a for a in asset_ids if asset_ids.count(a) > 1}
    for asset_id in sorted(duplicates):
        report.add(
            "error",
            CATALOG_SHEET,
            _loc_asset(asset_id),
            "duplicate_asset_id",
            "Zduplikowane asset_id w katalogu",
        )

    enabled = catalog.copy()
    if AnalyseAssetsCatalog.ENABLED in enabled.columns:
        try:
            enabled_mask = enabled[AnalyseAssetsCatalog.ENABLED].astype(bool)
            enabled = enabled.loc[enabled_mask]
        except (TypeError, ValueError):
            report.add(
                "error",
                CATALOG_SHEET,
                "enabled",
                "bad_enabled",
                "Kolumna enabled nie da się zrzutować na bool",
            )
            enabled = catalog.iloc[0:0]

    if not enabled.empty and AnalyseAssetsCatalog.ORDER in enabled.columns:
        orders = enabled[AnalyseAssetsCatalog.ORDER]
        if orders.duplicated().any():
            report.add(
                "warning",
                CATALOG_SHEET,
                "order",
                "duplicate_order",
                "Zduplikowane order wśród włączonych aktywów — sortowanie może być niestabilne",
            )

    return set(asset_ids)


def _validate_rule_value(field_name: str, operator: str, value, report: ValidationReport, loc: str) -> None:
    if is_blank_rule_value(value) and operator in {"contains", "contains_no_regex", "equals"}:
        report.add(
            "warning",
            RULES_SHEET,
            loc,
            "blank_value",
            f"Puste value dla {field_name}/{operator}",
        )
        return

    if operator == "contains":
        try:
            re.compile(str(value))
        except re.error as exc:
            report.add(
                "error",
                RULES_SHEET,
                loc,
                "bad_regex",
                f"Niepoprawny regex w value={value!r}: {exc}",
            )

    if field_name == "YEAR":
        text = str(value).strip()
        if not re.fullmatch(r"\d{4}", text):
            report.add(
                "warning",
                RULES_SHEET,
                loc,
                "year_format",
                f"YEAR zwykle jest 4-cyfrowe, jest {value!r}",
            )

    if field_name == "AMOUNT" or (
        field_name != "YEAR" and operator in {"gte", "gt", "lte", "lt"}
    ):
        if field_name == "YEAR":
            return
        try:
            float(value)
        except (TypeError, ValueError):
            report.add(
                "error",
                RULES_SHEET,
                loc,
                "non_numeric_value",
                f"value={value!r} musi być liczbą dla {field_name}/{operator}",
            )

    if field_name == "ACCOUNT_NUMBER" and not is_blank_rule_value(value):
        text = str(value).strip().replace(".0", "")
        if " " in text or not text.isdigit():
            report.add(
                "warning",
                RULES_SHEET,
                loc,
                "account_format",
                f"Numer konta zwykle to same cyfry bez spacji, jest {value!r}",
            )

    if field_name == "POOL_ID" and not is_blank_rule_value(value):
        text = str(value).strip()
        if text not in SUPPORTED_POOL_IDS and text != MANUAL_TRANSACTION_SOURCE:
            report.add(
                "warning",
                RULES_SHEET,
                loc,
                "source_filter_unknown",
                f"Selektor {field_name}={text!r} nie pasuje do znanych pool_id "
                f"{sorted(SUPPORTED_POOL_IDS)}",
            )


def _validate_rules(
    rules: pd.DataFrame,
    catalog: pd.DataFrame,
    catalog_ids: set[str],
    report: ValidationReport,
) -> None:
    catalog_source_by_id = {
        str(row[AnalyseAssetsCatalog.ASSET_ID]).strip(): _catalog_source(row)
        for _, row in catalog.iterrows()
        if not is_blank_rule_value(row.get(AnalyseAssetsCatalog.ASSET_ID))
    }

    for idx, row in rules.iterrows():
        asset_id = row.get(AnalyseAssetsRules.ASSET_ID)
        step_id = row.get(AnalyseAssetsRules.STEP_ID)
        loc = _loc_rule(asset_id, step_id, idx)

        if is_blank_rule_value(asset_id):
            report.add("error", RULES_SHEET, loc, "blank_asset_id", "Puste asset_id")
            continue
        asset_id = str(asset_id).strip()
        loc = _loc_rule(asset_id, step_id, idx)

        if asset_id not in catalog_ids:
            report.add(
                "error",
                RULES_SHEET,
                loc,
                "unknown_asset_id",
                "asset_id nie występuje w arkuszu assets",
            )

        mapping = rule_cell_str(row.get(AnalyseAssetsRules.MAPPING))
        if mapping is None:
            report.add("error", RULES_SHEET, loc, "blank_mapping", "Puste mapping")
        elif mapping not in MAPPING_NAMES or mapping not in MAPPING_MAP:
            report.add(
                "error",
                RULES_SHEET,
                loc,
                "unknown_mapping",
                f"mapping={mapping!r} nie jest zdefiniowane w procedurach "
                f"(dozwolone: {sorted(MAPPING_MAP)})",
            )

        field_name = rule_cell_str(row.get(AnalyseAssetsRules.FIELD))
        operator = rule_cell_str(row.get(AnalyseAssetsRules.OPERATOR))

        if field_name is None or operator is None:
            # read_analyse_config usuwa takie wiersze — tu nie powinno ich być
            report.add(
                "warning",
                RULES_SHEET,
                loc,
                "incomplete_rule",
                "Niepełna reguła (brak field/operator) — zostanie pominięta przy wczytaniu",
            )
            continue

        if field_name in LEGACY_FIELD_ALIASES:
            report.add(
                "error",
                RULES_SHEET,
                loc,
                "legacy_field",
                f"field={field_name!r} to alias wsteczny — użyj "
                f"{LEGACY_FIELD_ALIASES[field_name]!r}",
            )
        elif field_name not in CANONICAL_FIELDS:
            report.add(
                "error",
                RULES_SHEET,
                loc,
                "unknown_field",
                f"field={field_name!r} nie jest obsługiwane "
                f"(dozwolone: {sorted(CANONICAL_FIELDS)})",
            )
        if operator not in OPERATOR_NAMES:
            report.add(
                "error",
                RULES_SHEET,
                loc,
                "unknown_operator",
                f"operator={operator!r} nie jest obsługiwany "
                f"(dozwolone: {sorted(OPERATOR_NAMES)})",
            )

        rule_source = row.get(AnalyseAssetsRules.POOL_ID)
        if not is_blank_rule_value(rule_source):
            rule_source = str(rule_source).strip()
            if rule_source == MANUAL_TRANSACTION_SOURCE:
                report.add(
                    "error",
                    RULES_SHEET,
                    loc,
                    "invalid_rule_source",
                    f"pool_id={rule_source!r} jest zarezerwowane dla wierszy manual",
                )
            elif rule_source not in SUPPORTED_POOL_IDS:
                report.add(
                    "error",
                    RULES_SHEET,
                    loc,
                    "unsupported_source",
                    f"pool_id={rule_source!r} nie jest obsługiwane "
                    f"(puste=inherit, dozwolone: {sorted(SUPPORTED_POOL_IDS)})",
                )

        default_source = catalog_source_by_id.get(asset_id, DEFAULT_POOL_ID)
        effective = (
            str(rule_source).strip()
            if not is_blank_rule_value(row.get(AnalyseAssetsRules.POOL_ID))
            else default_source
        )
        allowed_fields = FIELDS_BY_SOURCE.get(effective)
        if (
            allowed_fields is not None
            and field_name is not None
            and field_name not in LEGACY_FIELD_ALIASES
            and field_name not in allowed_fields
        ):
            report.add(
                "error",
                RULES_SHEET,
                loc,
                "field_source_mismatch",
                f"field={field_name!r} nie pasuje do źródła {effective!r} "
                f"(dozwolone: {sorted(allowed_fields)})",
            )

        if field_name in OPERATORS_BY_FIELD and operator is not None:
            allowed_ops = OPERATORS_BY_FIELD[field_name]
            if operator not in allowed_ops:
                report.add(
                    "error",
                    RULES_SHEET,
                    loc,
                    "operator_field_mismatch",
                    f"operator={operator!r} nie jest typowy dla field={field_name!r} "
                    f"(oczekiwane: {sorted(allowed_ops)})",
                )

        if (
            field_name is not None
            and operator is not None
            and field_name in CANONICAL_FIELDS
        ):
            _validate_rule_value(
                field_name,
                operator,
                row.get(AnalyseAssetsRules.VALUE),
                report,
                loc,
            )

    if rules.empty:
        return

    group_cols = [
        AnalyseAssetsRules.ASSET_ID,
        AnalyseAssetsRules.STEP_ID,
        AnalyseAssetsRules.STEP_ORDER,
    ]
    for keys, step_rules in rules.groupby(group_cols, sort=False):
        asset_id, step_id, step_order = keys
        loc = f"asset_id={asset_id!r} step_id={step_id!r} step_order={step_order}"

        mappings = {
            str(v).strip()
            for v in step_rules[AnalyseAssetsRules.MAPPING].tolist()
            if not is_blank_rule_value(v)
        }
        if len(mappings) > 1:
            report.add(
                "error",
                RULES_SHEET,
                loc,
                "inconsistent_mapping",
                f"W jednym kroku różne mapping: {sorted(mappings)} "
                "(allocate bierze tylko pierwszy wiersz)",
            )

        pool_ids = {
            str(v).strip()
            for v in step_rules[AnalyseAssetsRules.POOL_ID].tolist()
            if not is_blank_rule_value(v)
        }
        if len(pool_ids) > 1:
            report.add(
                "error",
                RULES_SHEET,
                loc,
                "inconsistent_step_source",
                f"W jednym kroku różne pool_id: {sorted(pool_ids)} "
                "(obowiązuje pierwsze niepuste)",
            )


def _validate_manual(
    manual: pd.DataFrame,
    catalog_ids: set[str],
    report: ValidationReport,
) -> None:
    for idx, row in manual.iterrows():
        asset_id = row.get(AnalyseAssetsManual.ASSET_ID)
        loc = _loc_manual(asset_id, idx)

        if is_blank_rule_value(asset_id):
            report.add("error", MANUAL_SHEET, loc, "blank_asset_id", "Puste asset_id")
            continue
        asset_id = str(asset_id).strip()
        loc = _loc_manual(asset_id, idx)

        if asset_id not in catalog_ids:
            report.add(
                "error",
                MANUAL_SHEET,
                loc,
                "unknown_asset_id",
                "asset_id nie występuje w arkuszu assets",
            )

        category = rule_cell_str(row.get(AnalyseAssetsManual.CATEGORY))
        if category is None:
            report.add("error", MANUAL_SHEET, loc, "blank_category", "Puste category")
        elif category not in CATEGORY_NAMES:
            report.add(
                "error",
                MANUAL_SHEET,
                loc,
                "unknown_category",
                f"category={category!r} nie jest obsługiwane "
                f"(dozwolone: {sorted(CATEGORY_NAMES)})",
            )

        try:
            amount = float(row[AnalyseAssetsManual.AMOUNT])
        except (TypeError, ValueError):
            report.add(
                "error",
                MANUAL_SHEET,
                loc,
                "bad_amount",
                f"amount={row.get(AnalyseAssetsManual.AMOUNT)!r} musi być liczbą",
            )
            amount = None

        if amount is not None and category in _NEGATIVE_MANUAL_CATEGORIES and amount > 0:
            report.add(
                "error",
                MANUAL_SHEET,
                loc,
                "amount_sign",
                f"category={category} wymaga amount ≤ 0 (AssetRw.check_values), jest {amount}",
            )
        if amount is not None and category in _POSITIVE_MANUAL_CATEGORIES and amount < 0:
            report.add(
                "error",
                MANUAL_SHEET,
                loc,
                "amount_sign",
                f"category={category} wymaga amount ≥ 0 (AssetRw.check_values), jest {amount}",
            )

        try:
            parsed = pd.Timestamp(row[AnalyseAssetsManual.DATE])
            if pd.isna(parsed):
                raise ValueError("NaT")
        except (TypeError, ValueError):
            report.add(
                "error",
                MANUAL_SHEET,
                loc,
                "bad_date",
                f"date={row.get(AnalyseAssetsManual.DATE)!r} nie da się sparsować",
            )

        if is_blank_rule_value(row.get(AnalyseAssetsManual.DESCRIPTION)):
            report.add(
                "warning",
                MANUAL_SHEET,
                loc,
                "blank_description",
                "Puste description",
            )


def _validate_enabled_coverage(
    catalog: pd.DataFrame,
    rules: pd.DataFrame,
    manual: pd.DataFrame,
    report: ValidationReport,
) -> None:
    if catalog.empty:
        return
    enabled = catalog[catalog[AnalyseAssetsCatalog.ENABLED].astype(bool)]
    rule_assets = set(
        rules[AnalyseAssetsRules.ASSET_ID].astype(str).str.strip()
    ) if not rules.empty else set()
    manual_assets = set(
        manual[AnalyseAssetsManual.ASSET_ID].astype(str).str.strip()
    ) if not manual.empty else set()

    for _, row in enabled.iterrows():
        asset_id = str(row[AnalyseAssetsCatalog.ASSET_ID]).strip()
        if asset_id not in rule_assets and asset_id not in manual_assets:
            report.add(
                "warning",
                CATALOG_SHEET,
                _loc_asset(asset_id),
                "no_allocation",
                "Włączone aktywo nie ma reguł ani wierszy manual",
            )


def _validate_raw_incomplete_rules(raw_rules: pd.DataFrame, report: ValidationReport) -> None:
    if raw_rules.empty:
        return
    if AnalyseAssetsRules.FIELD not in raw_rules.columns:
        return
    if AnalyseAssetsRules.OPERATOR not in raw_rules.columns:
        return

    for idx, row in raw_rules.iterrows():
        field_blank = is_blank_rule_value(row.get(AnalyseAssetsRules.FIELD))
        operator_blank = is_blank_rule_value(row.get(AnalyseAssetsRules.OPERATOR))
        if field_blank or operator_blank:
            # Pomijamy całkowicie puste wiersze (częste w Excelu).
            meaningful = any(
                not is_blank_rule_value(row.get(col))
                for col in (
                    AnalyseAssetsRules.ASSET_ID,
                    AnalyseAssetsRules.STEP_ID,
                    AnalyseAssetsRules.MAPPING,
                    AnalyseAssetsRules.VALUE,
                )
                if col in raw_rules.columns
            )
            if not meaningful:
                continue
            report.add(
                "warning",
                RULES_SHEET,
                _loc_rule(row.get(AnalyseAssetsRules.ASSET_ID), row.get(AnalyseAssetsRules.STEP_ID), idx),
                "incomplete_rule_dropped",
                "Wiersz z pustym field/operator zostanie pominięty przy wczytaniu",
            )


def _validate_against_pool(
    catalog: pd.DataFrame,
    rules: pd.DataFrame,
    pool: pd.DataFrame,
    report: ValidationReport,
) -> None:
    """Opcjonalna walidacja względem poola (dziś mbank_pln)."""

    if pool is None or pool.empty:
        report.add(
            "warning",
            "pool",
            "-",
            "empty_pool",
            "Pool transakcji jest pusty — pominięto walidację selektorów",
        )
        return

    if AssetRw.YEAR not in pool.columns:
        pool = AssetRw.add_ymd_columns(pool.copy())
    if AccountTx.POOL_ID not in pool.columns:
        pool = pool.copy()
        pool[AccountTx.POOL_ID] = DEFAULT_POOL_ID

    enabled = catalog[catalog[AnalyseAssetsCatalog.ENABLED].astype(bool)]
    for _, asset_row in enabled.iterrows():
        asset_id = str(asset_row[AnalyseAssetsCatalog.ASSET_ID]).strip()
        default_source = _catalog_source(asset_row)
        asset_rules = rules[rules[AnalyseAssetsRules.ASSET_ID].astype(str).str.strip() == asset_id]
        if asset_rules.empty:
            continue

        remaining = pool.copy()
        for (step_id, step_order), step_rules in asset_rules.groupby(
            [AnalyseAssetsRules.STEP_ID, AnalyseAssetsRules.STEP_ORDER],
            sort=False,
        ):
            loc = f"asset_id={asset_id!r} step_id={step_id!r} step_order={step_order}"
            mapping_name = str(step_rules[AnalyseAssetsRules.MAPPING].iloc[0])
            effective = _step_effective_source(step_rules, default_source)
            if effective not in SUPPORTED_POOL_IDS:
                report.add(
                    "warning",
                    RULES_SHEET,
                    loc,
                    "pool_source_skip",
                    f"Krok pool_id={effective!r} — walidacja poola pominięta "
                    f"(obsługiwane: {sorted(SUPPORTED_POOL_IDS)})",
                )
                continue
            try:
                mapping = get_mapping(mapping_name)
                step_remaining = remaining[
                    remaining[AccountTx.POOL_ID].astype(str) == effective
                ].copy()
                other = remaining[
                    remaining[AccountTx.POOL_ID].astype(str) != effective
                ].copy()
                selector = build_step_selector(step_remaining, step_rules)
                step_remaining, _selected = select_asset(
                    step_remaining,
                    selector,
                    mapping,
                    asset_id=asset_id,
                    step_rules=step_rules,
                )
                remaining = pd.concat([step_remaining, other], ignore_index=True)
            except ValueError as exc:
                report.add(
                    "error",
                    RULES_SHEET,
                    loc,
                    "selector_runtime",
                    str(exc),
                )


def validate_analyse_config(
    config_path: Path | None = None,
    *,
    pool: pd.DataFrame | None = None,
    check_pool: bool = False,
) -> ValidationReport:
    """
    Waliduje analyse_assets_config.xlsx (tylko nowa struktura).

    Stare kody pól (MBANK_*, SOURCE) i kolumna ``source`` są błędami.

    :param config_path: ścieżka do xlsx (domyślnie Dropbox)
    :param pool: opcjonalny DataFrame transakcji (AccountTx)
    :param check_pool: gdy True, uruchamia selektory względem poola
    """
    path = get_config_file(config_path)
    report = ValidationReport(config_path=path)

    if not path.is_file():
        report.add(
            "error",
            "file",
            str(path),
            "missing_file",
            "Plik konfiguracji nie istnieje",
        )
        return report

    _validate_raw_schema(path, report)

    try:
        config = read_analyse_config(path)
    except Exception as exc:  # noqa: BLE001 — raportujemy dowolny błąd wczytania
        report.add(
            "error",
            "file",
            str(path),
            "load_failed",
            f"Nie udało się wczytać konfiguracji: {exc}",
        )
        return report

    catalog = config["catalog"]
    rules = config["rules"]
    manual = config["manual"]

    catalog_ids = _validate_catalog(catalog, report)
    _validate_rules(rules, catalog, catalog_ids, report)
    _validate_manual(manual, catalog_ids, report)
    _validate_enabled_coverage(catalog, rules, manual, report)

    if check_pool:
        if pool is None:
            frames = []
            for pool_id in sorted(
                {
                    _catalog_source(row)
                    for _, row in catalog.iterrows()
                    if bool(row.get(AnalyseAssetsCatalog.ENABLED, True))
                }
            ):
                if pool_id in SUPPORTED_POOL_IDS:
                    frames.append(load_accounts_pool(pool_id))
            pool = (
                pd.concat([f for f in frames if f is not None and not f.empty], ignore_index=True)
                if frames
                else load_accounts_pool(MBANK_PLN)
            )
        _validate_against_pool(catalog, rules, pool, report)

    return report


def format_report(report: ValidationReport) -> str:
    lines = [
        f"Config: {report.config_path}",
        f"Errors: {len(report.errors)}  Warnings: {len(report.warnings)}",
    ]
    if not report.issues:
        lines.append("OK - brak problemow.")
        return "\n".join(lines)
    for issue in report.issues:
        lines.append(issue.format())
    return "\n".join(lines)


def print_report(report: ValidationReport) -> None:
    print(format_report(report))
