import pandas as pd
import numpy as np
import re
from typing import List, Optional, Iterable


phrase_in  = "PRZELEW WEWNĘTRZNY PRZYCHODZĄCY"
phrases_out = ["PRZELEW WEWNĘTRZNY WYCHODZĄCY", "PRZELEW WŁASNY"]  # <= nowy wariant

def _contains_ci(text: str, phrase: str) -> bool:
    if pd.isna(text):
        return False
    return re.search(re.escape(phrase), str(text), flags=re.IGNORECASE) is not None


def _contains_any_ci(text: str, phrases: list[str]) -> bool:
    return any(_contains_ci(text, p) for p in phrases)


def consolidate_many_drop_internal_transfers(
    statements: List[pd.DataFrame],
    *,
    col_konto_bazowe="Konto bazowe",
    col_numer_konta="#Numer konta",
    col_kwota="#Kwota",
    col_data_transakcji="Data transakcji",   # fallback do '#Data operacji' gdy brak
    col_tytul="#Tytuł",                      # opcjonalne (pomaga w rozróżnianiu wielu podobnych transakcji)
    col_opis="#Opis operacji",               # kluczowe: IN/OUT
    phrase_in="PRZELEW WEWNĘTRZNY PRZYCHODZĄCY",
    phrase_out="PRZELEW WEWNĘTRZNY WYCHODZĄCY",
    date_tolerance="D",                      # 'D' dzień, 'H' godzina, 'T' minuty, 'S' sekundy, 'exact'
    require_opposite_sign=True,
    owned_accounts: Optional[Iterable[str]] = None,  # jeżeli chcesz ograniczyć do własnych kont
    also_key_by_currency: Optional[str] = None       # np. 'Waluta' jeśli masz multi-currency
):

    df = pd.concat(statements, ignore_index=True)

    df[col_data_transakcji] = pd.to_datetime(df[col_data_transakcji], errors="coerce")

    df["_sign"] = np.where(df[col_kwota] >= 0, 1, -1)
    df["_amount_abs"] = df[col_kwota].abs()

    df["_bucket_time"] = df[col_data_transakcji].dt.floor(date_tolerance)

    # 4) ogranicz do własnych kont (opcjonalnie)
    if owned_accounts is not None:
        owned_accounts = set(map(str, owned_accounts))
        df = df[df[col_konto_bazowe].astype(str).isin(owned_accounts)]

    # 5) wykryj przelewy wewnętrzne z opisu
    def _contains(text, phrase):
        if pd.isna(text): return False
        return re.search(re.escape(phrase), str(text), flags=re.IGNORECASE) is not None

    df["_internal_in"] = df[col_opis].map(lambda x: _contains_ci(x, phrase_in))
    df["_internal_out"] = df[col_opis].map(lambda x: _contains_any_ci(x, phrases_out))

    df["_internal_type"] = np.select(
        [df["_internal_in"], df["_internal_out"]],
        ["IN", "OUT"],
        default=""
    )
    # po zbudowaniu df i wykryciu _internal_type
    internal = df[df["_internal_type"].isin(["IN", "OUT"])].copy()
    external = df[~df.index.isin(internal.index)].copy()  # <--- DODAJ TO

    # odfiltruj samo-przelewy
    mask_self = internal[col_konto_bazowe].astype(str) != internal[col_numer_konta].astype(str)
    internal = internal[mask_self].copy()

    # TERAZ dopiero buduj a/b
    a = internal[col_konto_bazowe].astype(str).to_numpy()
    b = internal[col_numer_konta].astype(str).to_numpy()

    internal["_acc_min"] = np.where(a < b, a, b)
    internal["_acc_max"] = np.where(a < b, b, a)

    # (opcjonalnie) normalizacja tytułu, by rozróżniać wiele identycznych pozycji
    if col_tytul in internal.columns:
        tkey = (internal[col_tytul].fillna("")
                .astype(str).str.lower().str.replace(r"\s+", " ", regex=True).str[:40])
    else:
        tkey = ""

    # (opcjonalnie) klucz po walucie
    # currency_part = ""
    if also_key_by_currency and also_key_by_currency in internal.columns:
        currency_part = "||" + internal[also_key_by_currency].astype(str)
    else:
        currency_part = ""

    internal["_pair_bucket"] = (
        internal["_acc_min"] + "||" + internal["_acc_max"] + "||" +
        internal["_bucket_time"].astype(str) + "||" +
        internal["_amount_abs"].astype(str) +
        currency_part + "||" +
        (tkey if isinstance(tkey, str) else tkey)
    )

    # 7) IN vs OUT i parowanie 1-do-1 w kubełku
    internal["_row_id"] = internal.index  # zapisz oryginalny indeks do późniejszego dropu

    df_in  = internal[internal["_internal_type"] == "IN"].copy()
    df_out = internal[internal["_internal_type"] == "OUT"].copy()

    # sanity: zgodność znaku vs opis (do raportu)
    df_in["_sign_ok"]  = (df_in["_sign"]  >= 0)
    df_out["_sign_ok"] = (df_out["_sign"] <= 0)

    df_in["_rank"]  = df_in.groupby("_pair_bucket").cumcount()
    df_out["_rank"] = df_out.groupby("_pair_bucket").cumcount()

    pairs = pd.merge(
        df_in, df_out,
        on=["_pair_bucket", "_rank"],
        suffixes=("_in", "_out"),
        how="inner"
    )

    if require_opposite_sign:
        pairs = pairs[pairs["_sign_in"] != pairs["_sign_out"]]

    # 8) usuń obie strony sparowanych przelewów
    to_drop = set(pairs["_row_id_in"].tolist()) | set(pairs["_row_id_out"].tolist())

    # 9) raport i wynik
    report = pairs[[
        "_pair_bucket",
        col_data_transakcji + "_in", col_kwota + "_in", col_konto_bazowe + "_in", col_numer_konta + "_in", "_source_in", "_sign_ok_in",
        col_data_transakcji + "_out", col_kwota + "_out", col_konto_bazowe + "_out", col_numer_konta + "_out", "_source_out", "_sign_ok_out",
    ]].rename(columns={
        col_data_transakcji + "_in": "data_in",
        col_kwota + "_in": "kwota_in",
        col_konto_bazowe + "_in": "konto_bazowe_in",
        col_numer_konta + "_in": "numer_konta_in",
        "_source_in": "zrodlo_in",
        "_sign_ok_in": "opis_vs_znak_in",
        col_data_transakcji + "_out": "data_out",
        col_kwota + "_out": "kwota_out",
        col_konto_bazowe + "_out": "konto_bazowe_out",
        col_numer_konta + "_out": "numer_konta_out",
        "_source_out": "zrodlo_out",
        "_sign_ok_out": "opis_vs_znak_out",
    }).copy()

    cleaned_internal = internal.drop(index=list(to_drop))
    cleaned = pd.concat([external, cleaned_internal], ignore_index=False)

    # cleaned = cleaned.drop(columns=[
    #     "_sign","_amount_abs","_bucket_time","_acc_min","_acc_max",
    #     "_internal_in","_internal_out","_internal_type"
    # ], errors="ignore").sort_values(by=[col_data_transakcji]).reset_index(drop=True)

    meta = {
        "input_rows": sum(len(x) for x in statements),
        "candidates_internal": len(internal),
        "pairs_removed": len(pairs),
        "rows_removed": len(to_drop),
        "output_rows": len(cleaned),
        "matching": {
            "uses_description": True,
            "phrase_in": phrase_in,
            "phrase_out": phrase_out,
            "date_tolerance": date_tolerance,
            "require_opposite_sign": require_opposite_sign,
            "also_key_by_currency": also_key_by_currency is not None
        }
    }
    return cleaned, report, meta
