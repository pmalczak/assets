# -*- coding: utf-8 -*-
"""
Eksportuje biezaca parametryzacje analyse_assets do pliku Excel.

Uzycie:
  cd app
  uv run python maintenance/export_analyse_assets_config.py
  uv run python maintenance/export_analyse_assets_config.py C:/sciezka/analyse_assets_config.xlsx
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

APP_ROOT = Path(__file__).resolve().parent.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from analyse_assets.config_model import (
    CONFIG_FILE_NAME,
    CATALOG_SHEET,
    DEFAULT_POOL_ID,
    MANUAL_SHEET,
    MBANK_EUR_TRANSACTION_SOURCE,
    RULES_SHEET,
)
from app_proc.data_root import get_online_data_root


def _catalog() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"asset_id": "aquamarina", "output_file": "mbank_aquamarina.xlsx", "order": 1, "enabled": 1, "properties_id": "aquamarina", "pool_id": DEFAULT_POOL_ID},
            {"asset_id": "horbaczewskiego", "output_file": "mbank_horbaczewskiego.xlsx", "order": 2, "enabled": 1, "properties_id": "horbaczewskiego", "pool_id": DEFAULT_POOL_ID},
            {"asset_id": "garaz", "output_file": "mbank_garaz.xlsx", "order": 3, "enabled": 1, "properties_id": "garaż", "pool_id": DEFAULT_POOL_ID},
            {"asset_id": "starogajowa", "output_file": "mbank_starogajowa.xlsx", "order": 4, "enabled": 1, "properties_id": "starogajowa", "pool_id": DEFAULT_POOL_ID},
            {"asset_id": "kiemliczow_1", "output_file": "mbank_kiemliczow_1.xlsx", "order": 5, "enabled": 1, "properties_id": "kiemliczow_1", "pool_id": DEFAULT_POOL_ID},
            {"asset_id": "kiemliczow_4", "output_file": "mbank_kiemliczow_4.xlsx", "order": 6, "enabled": 1, "properties_id": "kiemliczów_9_4", "pool_id": DEFAULT_POOL_ID},
            {"asset_id": "kiemliczow_3", "output_file": "mbank_kiemliczow_3.xlsx", "order": 7, "enabled": 1, "properties_id": "kiemliczów_9_3", "pool_id": DEFAULT_POOL_ID},
            {"asset_id": "rumiankowa", "output_file": "mbank_rumiankowa.xlsx", "order": 8, "enabled": 1, "properties_id": "rumiankowa", "pool_id": DEFAULT_POOL_ID},
            {"asset_id": "opoczynska", "output_file": "mbank_opoczynska.xlsx", "order": 9, "enabled": 1, "properties_id": "opoczyńska", "pool_id": DEFAULT_POOL_ID},
            {"asset_id": "karpacz", "output_file": "mbank_karpacz.xlsx", "order": 10, "enabled": 1, "properties_id": "karpacz", "pool_id": DEFAULT_POOL_ID},
            {"asset_id": "cash", "output_file": "mbank_cash.xlsx", "order": 11, "enabled": 1, "properties_id": "cash", "pool_id": MBANK_EUR_TRANSACTION_SOURCE},
        ]
    )


def _rule(
    asset_id: str,
    step_id: str,
    step_order: int,
    mapping: str,
    condition_group: int,
    field: str,
    operator: str,
    value,
    uwagi: str = "",
    pool_id: str = "",
) -> dict:
    return {
        "asset_id": asset_id,
        "step_id": step_id,
        "step_order": step_order,
        "mapping": mapping,
        "condition_group": condition_group,
        "field": field,
        "operator": operator,
        "value": value,
        "Uwagi": uwagi,
        "pool_id": pool_id,
    }


def _rules() -> pd.DataFrame:
    rows: list[dict] = []

    def add(*args):
        rows.append(_rule(*args))

    # aquamarina
    add("aquamarina", "r0", 0, "initial_investment", 1, "MBANK_TITLE", "contains", "UMOWA NR AQ/2014/252/180 LOKAL 180")
    # MIĘDZYZDROJE — literówka względem „Międzyzdroje” (zachowana w regułach)
    for i, v in enumerate(["AQUAMARINA", "MIĘDZYZDROJE", "MARINA INVEST", "KORNELIA ZAJĄCZKOWSKA"], start=1):
        add("aquamarina", "r1", 1, "inflow_outflow", i, "MBANK_TRANSACTION_PARTY", "contains", v)
    add("aquamarina", "r2", 2, "inflow_outflow", 1, "MBANK_ACCOUNT_NUMBER", "contains", "10124069600163204573190024")
    add("aquamarina", "r3", 3, "inflow_outflow", 1, "MBANK_TITLE", "contains", "ZALICZKA DO ZLECENIA 20020793 ZA NAROŻNIK I MATERAC")

    # horbaczewskiego
    add("horbaczewskiego", "r1", 0, "initial_investment", 1, "MBANK_ACCOUNT_NUMBER", "equals", "07124067263111001055248115")
    add("horbaczewskiego", "r1", 0, "initial_investment", 2, "MBANK_ACCOUNT_NUMBER", "equals", "33124067261111001052301556")
    add("horbaczewskiego", "r2", 1, "inflow_outflow", 1, "MBANK_ACCOUNT_NUMBER", "equals", "28114020040000390279513454")
    add("horbaczewskiego", "r2", 1, "inflow_outflow", 2, "MBANK_ACCOUNT_NUMBER", "equals", "41102052421283117588515063")
    add("horbaczewskiego", "r2", 1, "inflow_outflow", 3, "MBANK_ACCOUNT_NUMBER", "equals", "45105000996029010194551607")
    add("horbaczewskiego", "r3", 2, "inflow_outflow", 1, "MBANK_TITLE", "contains", "ZA MIESZKANIE")
    add("horbaczewskiego", "r3", 2, "inflow_outflow", 1, "MBANK_TRANSACTION_PARTY", "contains", "FILIP MALCZAK  UL.KIEMLICZÓW 9 M.4")
    add("horbaczewskiego", "r5", 3, "closing_investment", 1, "MBANK_TITLE", "contains", "DEPOZYT NOTARIALNY")
    add("horbaczewskiego", "r5", 3, "closing_investment", 1, "MBANK_TRANSACTION_PARTY", "contains", "KANCELARIA NOTARIALNA NATALIA ŁYSZCZAK ANNA PIKUŁA-SZUBA")
    add("horbaczewskiego", "r5", 3, "closing_investment", 2, "MBANK_TITLE", "contains", "ZALICZKA MIESZKANIE")
    add("horbaczewskiego", "r5", 3, "closing_investment", 2, "MBANK_TRANSACTION_PARTY", "contains", "BEDEKIER JACEK STANISŁAW           I BEDEKIER JUSTYNA")

    # garaz
    add("garaz", "r0", 0, "initial_investment", 1, "MBANK_TITLE", "contains", "OPŁATA ZA ZAKUP GARAŻU - UL. RUMIANKOWA")
    add("garaz", "r1", 1, "inflow_outflow", 1, "MBANK_TRANSACTION_PARTY", "contains", "IGLICA GARAŻ")
    add("garaz", "r1", 1, "inflow_outflow", 2, "MBANK_TRANSACTION_PARTY", "contains", "PODATEK GARAŻ")
    add("garaz", "r2", 2, "inflow_outflow", 1, "MBANK_TITLE", "contains", "GARAŻ")
    add("garaz", "r2", 2, "inflow_outflow", 1, "YEAR", "gte", "2020")
    add("garaz", "r2", 2, "inflow_outflow", 2, "MBANK_TITLE", "equals", "OPŁATA ZA ZAKUP GARAŻU - UL. RUMIANKOWA")
    add("garaz", "r2", 2, "inflow_outflow", 3, "MBANK_TITLE", "contains", "GARAŻ ZA")

    # starogajowa
    for i, title in enumerate(
        [
            "ZADATEK-UMOWA PRZEDWSTĘPNA-SPRZEDAŻ STAROGAJOWA 23",
            "DEPOZYT DO UMOWY SPRZEDAŻY STAROGAJOWA 23",
            "FV73/2019",
            "OPŁATA NOTARIALNA + PODATEK ZA SPRZEDAŻ STAROGAJOWA 23",
        ],
        start=1,
    ):
        add("starogajowa", "r1", 0, "initial_investment", i, "MBANK_TITLE", "contains", title)
    add("starogajowa", "r2", 1, "inflow_outflow", 1, "MBANK_TITLE", "contains", "STAROGAJOWA")
    for i, account in enumerate(
        [
            "06102010269321202107100005",
            "04102010269000000022415575",
            "14109000048377000072886502",
            "78102052269493000000357543",
        ],
        start=2,
    ):
        add("starogajowa", "r2", 1, "inflow_outflow", i, "MBANK_ACCOUNT_NUMBER", "equals", account)
    add("starogajowa", "r3", 2, "inflow_outflow", 1, "MBANK_TRANSACTION_PARTY", "contains", "PGNIG STAROGAJOWA INDYWIDUALNE KONTO")
    add("starogajowa", "r3", 2, "inflow_outflow", 2, "MBANK_TRANSACTION_PARTY", "contains", "TAURON STAROGAJOWA")
    add("starogajowa", "r3", 2, "inflow_outflow", 3, "MBANK_TRANSACTION_PARTY", "contains", "MPWIK STAROGAJOWA")

    # kiemliczow_3
    add("kiemliczow_3", "r1", 1, "initial_investment", 1, "MBANK_TRANSACTION_PARTY", "contains", "GRZEGORZ KOPACKI")
    add("kiemliczow_3", "r1", 1, "initial_investment", 2, "MBANK_TRANSACTION_PARTY", "contains", "GRZEGORZ I AGATA KOPACCY")
    add("kiemliczow_3", "r2", 2, "inflow_outflow", 1, "MBANK_TITLE", "contains", "KIEMLICZÓW 9/3")
    add("kiemliczow_3", "r2", 2, "inflow_outflow", 2, "MBANK_TRANSACTION_PARTY", "contains", "WOJCIECH GOŁĘBIOWSKI  UL.ŚCIEGIENNEGO 69 M.38            30-809 KRAKÓW")
    add("kiemliczow_3", "r2", 2, "inflow_outflow", 3, "MBANK_TITLE", "contains", "ROZLICZENIE KAUCJI")
    add("kiemliczow_3", "r2", 2, "inflow_outflow", 4, "MBANK_TRANSACTION_PARTY", "contains", "GOŁĘBIOWSKI")
    add("kiemliczow_3", "r2", 2, "inflow_outflow", 5, "MBANK_TRANSACTION_PARTY", "contains", "KRZYSZTOF TUTAJ")
    add("kiemliczow_3", "r2", 2, "inflow_outflow", 6, "MBANK_TRANSACTION_PARTY", "contains", "STANISŁAW EDMUND TUTAJ")
    add("kiemliczow_3", "r2", 2, "inflow_outflow", 7, "MBANK_TRANSACTION_PARTY", "contains", "STANISŁAW TUTAJ")
    add("kiemliczow_3", "r2", 2, "inflow_outflow", 8, "MBANK_ACCOUNT_NUMBER", "equals", "78102010264322413325710019")
    add("kiemliczow_3", "r2", 2, "inflow_outflow", 9, "MBANK_ACCOUNT_NUMBER", "equals", "20109027500000000141901493")
    add("kiemliczow_3", "r2", 2, "inflow_outflow", 10, "MBANK_ACCOUNT_NUMBER", "equals", "72102049000000840235213880")

    # kiemliczow_4
    add("kiemliczow_4", "r1", 1, "inflow_outflow", 1, "MBANK_TITLE", "contains", "KIEMLICZÓW 9/4")
    add("kiemliczow_4", "r1", 1, "inflow_outflow", 2, "MBANK_TITLE", "contains_no_regex", "CZYNSZ + POMIESZCZENIE GOSPODARCZE (51,00)")
    add("kiemliczow_4", "r1", 1, "inflow_outflow", 3, "MBANK_TRANSACTION_PARTY", "equals", "TAURON KIEMLICZÓW 4 ")
    add("kiemliczow_4", "r2", 2, "inflow_outflow", 1, "MBANK_ACCOUNT_NUMBER", "equals", "78102010264322424265110059")
    add("kiemliczow_4", "r2", 2, "inflow_outflow", 2, "MBANK_ACCOUNT_NUMBER", "equals", "47114010100000531029001001")
    add("kiemliczow_4", "r2", 2, "inflow_outflow", 3, "MBANK_ACCOUNT_NUMBER", "equals", "31105000996029010224308549")
    add("kiemliczow_4", "r3", 3, "inflow_outflow", 1, "MBANK_ACCOUNT_NUMBER", "equals", "20102052420000250201100809")
    add("kiemliczow_4", "r3", 3, "inflow_outflow", 2, "MBANK_TITLE", "equals", "WPŁATA NA FUNDUSZ BUDOWY DROGI PRZY UL. KIEMLICZÓW")

    # rumiankowa
    add("rumiankowa", "r1", 0, "inflow_outflow", 1, "MBANK_ACCOUNT_NUMBER", "equals", "26234000091290401000003553")
    add("rumiankowa", "r1", 0, "inflow_outflow", 2, "MBANK_ACCOUNT_NUMBER", "equals", "77249000050000400032972350")
    add("rumiankowa", "r2", 1, "inflow_outflow", 1, "MBANK_TITLE", "contains", "WKŁAD WŁASNY NA POCZET ZAKUPU MIESZKANIA UL. RUMIANKOWA 57D/4 WROCŁAW")
    add("rumiankowa", "r2", 1, "inflow_outflow", 2, "MBANK_TITLE", "contains", "ZAKUP LOKALU MIESZKALNEGO NR 4, WROCŁAW, UL. RUMIANKOWA 57D, REP A 1684/2019")
    add("rumiankowa", "r2", 1, "inflow_outflow", 3, "MBANK_TITLE", "contains", "DEC.129/2017; RUMIANKOWA 57D/4PRZEKSZ. UŻ WIECZ W PRAWO WŁ")
    add("rumiankowa", "r3", 2, "inflow_outflow", 1, "MBANK_TITLE", "contains", "RUMIANKOWA 57D")
    add("rumiankowa", "r3", 2, "inflow_outflow", 1, "MBANK_TRANSACTION_PARTY", "contains", "IGLICA")
    add("rumiankowa", "r3", 2, "inflow_outflow", 2, "MBANK_TITLE", "contains", "PRZEKSIĘGOWANIE NADWYŻKI PO SPŁACIEKREDYTU")
    add("rumiankowa", "r3", 2, "inflow_outflow", 2, "MBANK_TRANSACTION_PARTY", "contains", "RAIFFEISEN BANK INT. AG")
    add("rumiankowa", "r3", 2, "inflow_outflow", 3, "MBANK_TRANSACTION_PARTY", "contains", "PGNIG-RUMIANKOWA")
    add("rumiankowa", "r3", 2, "inflow_outflow", 4, "MBANK_TITLE", "contains", "UL RUMIANKOWA 57 D/4 - GAZ ENERGIA ELELKTRYCZNA")
    add("rumiankowa", "r3", 2, "inflow_outflow", 5, "MBANK_TITLE", "contains", "CZYNSZ - LOKAL RUMIANKOWA 57/D")
    add("rumiankowa", "r4", 3, "inflow_outflow", 1, "MBANK_TITLE", "contains", "WYNAJEM LOKALU")
    add("rumiankowa", "r4", 3, "inflow_outflow", 1, "MBANK_TRANSACTION_PARTY", "contains", "GPM SYSTEMY")
    add("rumiankowa", "r4", 3, "inflow_outflow", 2, "MBANK_TITLE", "contains", "RACH")
    add("rumiankowa", "r4", 3, "inflow_outflow", 2, "MBANK_AMOUNT", "equals", 2200.0)
    add("rumiankowa", "r4", 3, "inflow_outflow", 3, "MBANK_TITLE", "contains", "RACH")
    add("rumiankowa", "r4", 3, "inflow_outflow", 3, "MBANK_AMOUNT", "equals", 2750.0)
    add("rumiankowa", "r4", 3, "inflow_outflow", 4, "MBANK_TITLE", "contains", "RACH")
    add("rumiankowa", "r4", 3, "inflow_outflow", 4, "MBANK_AMOUNT", "equals", 250.0)

    # opoczynska
    add("opoczynska", "r1", 0, "initial_investment", 1, "MBANK_TITLE", "equals", "UMOWA KREDYTOWA E0891681 KREDYTOBIORCA MARCIN TYNECKI")
    add("opoczynska", "r1", 0, "initial_investment", 2, "MBANK_TITLE", "equals", "KUPNO MIESZKANIA OPOCZYŃSKA 14/14")
    add("opoczynska", "r2", 1, "investment_refund", 1, "MBANK_TITLE", "equals", "DAROWIZNA")
    add("opoczynska", "r2", 1, "investment_refund", 1, "MBANK_TRANSACTION_PARTY", "contains", "KRYSTYNA MALCZAK")
    add("opoczynska", "r2", 1, "investment_refund", 1, "YEAR", "equals", "2022")
    add("opoczynska", "r2", 1, "investment_refund", 1, "MBANK_AMOUNT", "gt", 0)
    add("opoczynska", "r3", 2, "inflow_outflow", 1, "MBANK_ACCOUNT_NUMBER", "equals", "43105000996029010240832283")
    add("opoczynska", "r3", 2, "inflow_outflow", 2, "MBANK_ACCOUNT_NUMBER", "equals", "78102010264322425711480066")
    add("opoczynska", "r4", 3, "inflow_outflow", 1, "MBANK_TRANSACTION_PARTY", "contains", "PODATEK OPOCZYŃSKA")
    add("opoczynska", "r4", 3, "inflow_outflow", 2, "MBANK_TRANSACTION_PARTY", "contains", "ZAUŁEK ZŁOTNICKI III")
    add("opoczynska", "r4", 3, "inflow_outflow", 3, "MBANK_TRANSACTION_PARTY", "contains", "MOICO")
    add("opoczynska", "r4", 3, "inflow_outflow", 4, "MBANK_TITLE", "contains", "ZWROT ZA RACHUNKI")
    add("opoczynska", "r4", 3, "inflow_outflow", 5, "MBANK_TITLE", "contains", "ZWROT ZA R-KI")

    # karpacz
    add("karpacz", "r1", 0, "initial_investment", 1, "MBANK_ACCOUNT_NUMBER", "equals", "87114020040000330286652080")
    add("karpacz", "r3", 1, "inflow_outflow", 1, "MBANK_ACCOUNT_NUMBER", "equals", "39105017511000009755659050")
    add("karpacz", "r3", 1, "inflow_outflow", 2, "MBANK_ACCOUNT_NUMBER", "equals", "52105000997198105701000230")

    # cash (mbank EUR g_m_56_3217_eur) — zasilenia kapitału
    add("cash", "r0", 0, "initial_investment", 1, "ACCOUNT_ID", "equals", "g_m_56_3217_eur")
    add("cash", "r0", 0, "initial_investment", 1, "TITLE", "contains", "DYWIDENDA")
    add("cash", "r0", 0, "initial_investment", 2, "ACCOUNT_ID", "equals", "g_m_56_3217_eur")
    add("cash", "r0", 0, "initial_investment", 2, "TITLE", "contains", "FINGO EARN OUT")
    add("cash", "r0", 0, "initial_investment", 3, "ACCOUNT_ID", "equals", "g_m_56_3217_eur")
    add("cash", "r0", 0, "initial_investment", 3, "OPERATION_TYPE", "equals", "PRZELEW WALUTOWY PRZYCHODZĄCY")
    add("cash", "r0", 0, "initial_investment", 3, "AMOUNT", "gte", 1000)

    return pd.DataFrame(rows)


def _manual() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"asset_id": "kiemliczow_1", "step_order": 0, "date": "1997-06-02", "amount": -48600.0, "category": "INVESTMENT", "description": "zakup mieszkania [54m2]"},
            {"asset_id": "kiemliczow_1", "step_order": 0, "date": "2000-01-03", "amount": 156600.0, "category": "CLOSING", "description": "sprzedaż"},
            {"asset_id": "kiemliczow_1", "step_order": 0, "date": "2000-04-04", "amount": -3700.0, "category": "OUTFLOW", "description": "opłata skarbowa"},
            {"asset_id": "kiemliczow_1", "step_order": 0, "date": "2000-04-04", "amount": -695.5, "category": "OUTFLOW", "description": "prowizja"},
            {"asset_id": "kiemliczow_1", "step_order": 0, "date": "2001-08-20", "amount": -572.5, "category": "OUTFLOW", "description": "hipoteka - opłata sądowa"},
            {"asset_id": "kiemliczow_1", "step_order": 0, "date": "2001-10-05", "amount": -145.0, "category": "OUTFLOW", "description": "hipoteka - opłata sądowa"},
            {"asset_id": "kiemliczow_3", "step_order": 0, "date": "2012-05-28", "amount": -7290.0, "category": "OUTFLOW", "description": "OPŁATA NOTARIALNA I PODATKI / GOTÓWKA"},
            {"asset_id": "kiemliczow_3", "step_order": 0, "date": "2012-05-28", "amount": -200.0, "category": "OUTFLOW", "description": "WYPIS Z KW / GOTÓWKA"},
            {"asset_id": "kiemliczow_3", "step_order": 0, "date": "2012-06-13", "amount": -1904.29, "category": "OUTFLOW", "description": "ZAKUP OKIEN DO MIESZK B.JASI / GOTÓWKA"},
            {"asset_id": "kiemliczow_4", "step_order": 0, "date": "2000-02-18", "amount": -185000.0, "category": "INVESTMENT", "description": "zakup mieszkania"},
            {
                "asset_id": "rumiankowa",
                "step_order": 0,
                "date": "2008-02-19",
                "amount": 326601.45,
                "category": "CLOSING",
                "description": "sprzedane (rozliczenie jako spłata kredytu)",
            },
        ]
    )


def main() -> None:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else get_online_data_root() / CONFIG_FILE_NAME
    sheets = {
        CATALOG_SHEET: _catalog(),
        RULES_SHEET: _rules(),
        MANUAL_SHEET: _manual(),
    }
    with pd.ExcelWriter(target, engine="openpyxl") as writer:
        for sheet_name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=sheet_name, index=False)
    print(f"Utworzono: {target.resolve()}")


if __name__ == "__main__":
    main()
