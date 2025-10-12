# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path
import pandas as pd
import numpy as np
import re

from assets.data_model import AssetsFile
from assets.read_assets import read_assets
from consolidate_and_drop_internal_transfers import consolidate_many_drop_internal_transfers
from data_root import get_online_data_root
from data_step.data_step import DATA_STEP
from importers.mbank.read_m_transactions import read_m_transactions

pd.options.mode.copy_on_write = True
pd.options.future.infer_string = True


def main():
    proj_root = Path(__file__).parent.parent
    DATA_STEP.init_steps(root=proj_root)

    assets = read_assets()
    assets = assets[assets[AssetsFile.KIND] == 'mbank_import']
    assets = assets[assets[AssetsFile.CURRENCY] == 'pln']
    assets = assets[AssetsFile.ID].tolist()

    data_root = get_online_data_root()
    result = []
    for asset in assets:
        df = read_m_transactions(data_root, asset)
        df["_source"] = asset

        result += [df]

    cleaned, report, meta = consolidate_many_drop_internal_transfers(result)
    print(meta)

    # df = pd.concat([df1, df2])
    p = Path(__file__).parent
    fout = p / f'mbank_consolidated.xlsx'
    cleaned.to_excel(fout, index=False)
    return


def consolidate_and_drop_internal_transfers(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    *,
    col_konto_bazowe="Konto bazowe",
    col_numer_konta="#Numer konta",       # <- dopasuj jeśli inaczej
    col_kwota="#Kwota",
    col_data_transakcji="Data transakcji", # fallback do '#Data operacji' jeśli brak
    col_tytul="#Tytuł",                    # opcjonalnie w kubełku
    col_opis="#Opis operacji",             # TU ważna kolumna
    phrase_in="PRZELEW WEWNĘTRZNY PRZYCHODZĄCY",
    phrase_out="PRZELEW WEWNĘTRZNY WYCHODZĄCY",
    # date_tolerance="D",                    # 'D' dzień, 'H' godzina, 'exact' dokładny timestamp
    # require_opposite_sign=True,            # czy wymagać przeciwnego znaku kwoty
):
    # 1) sklej
    df = pd.concat([df1.assign(_source="df1"), df2.assign(_source="df2")], ignore_index=True)

    df[col_data_transakcji] = pd.to_datetime(df[col_data_transakcji], errors="coerce")

    df["_sign"] = np.where(df[col_kwota] >= 0, 1, -1)
    df["_amount_abs"] = df[col_kwota].abs()

    # 4) kubełek czasu
    # if date_tolerance in ("D", "H", "T", "S"):
    df["_bucket_time"] = df[col_data_transakcji]  #.dt.floor(date_tolerance)
    # else:
    #     df["_bucket_time"] = df[col_data_transakcji]

    # 5) znacznik przelewu wewnętrznego wg #Opis operacji
    #    Robimy dopasowanie case-insensitive i tolerujemy dodatkowe słowa.
    def _contains(text, phrase):
        if pd.isna(text): return False
        return re.search(re.escape(phrase), str(text), flags=re.IGNORECASE) is not None

    df["_internal_in"]  = df[col_opis].map(lambda x: _contains(x, phrase_in))
    df["_internal_out"] = df[col_opis].map(lambda x: _contains(x, phrase_out))
    df["_internal_type"] = np.select(
        [df["_internal_in"], df["_internal_out"]],
        ["IN", "OUT"],
        default=""
    )
    # kandydaci do parowania tylko jeśli opis wskazuje na przelew wewnętrzny
    internal = df[df["_internal_type"].isin(["IN", "OUT"])].copy()
    internal["_row_id"] = internal.index
    external = df[~df.index.isin(internal.index)].copy()  # przechodzi bez zmian

    # 6) budowa klucza: te same dwa konta (w kolejności posortowanej), kwota abs, kubełek czasu
    a = internal[col_konto_bazowe].astype(str)
    b = internal[col_numer_konta].astype(str)
    internal["_acc_min"] = np.where(a < b, a, b)
    internal["_acc_max"] = np.where(a < b, b, a)

    # if col_tytul in internal.columns:
    tkey = (internal[col_tytul].fillna("")
            .astype(str).str.lower().str.replace(r"\s+", " ", regex=True).str[:40])
    # else:
    #     tkey = ""

    internal["_pair_bucket"] = (
        internal["_acc_min"] + "||" + internal["_acc_max"] + "||" +
        internal["_bucket_time"].astype(str) + "||" +
        internal["_amount_abs"].astype(str) + "||" +
        (tkey if isinstance(tkey, str) else tkey)
    )

    # 7) rozdział na IN/OUT i parowanie 1-1 w obrębie kubełka
    df_in = internal[internal["_internal_type"] == "IN"].copy()
    df_out = internal[internal["_internal_type"] == "OUT"].copy()

    df_in["_rank"] = df_in.groupby("_pair_bucket").cumcount()
    df_out["_rank"] = df_out.groupby("_pair_bucket").cumcount()

    # (opcjonalnie) sprawdź zgodność znaku z opisem — tylko do raportu
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

    # Jeśli wymagamy przeciwnych znaków — odfiltruj pary o tym samym znaku
    # if require_opposite_sign:
    pairs = pairs[pairs["_sign_in"] != pairs["_sign_out"]]

    # 8) do usunięcia obie strony pary
    to_drop = set(pairs["_row_id_in"].tolist()) | set(pairs["_row_id_out"].tolist())

    # 9) raport
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

    # 10) wynik
    cleaned = pd.concat([external, internal.drop(index=list(to_drop))], ignore_index=False)
    cleaned = cleaned.drop(columns=[
        "_sign","_amount_abs","_bucket_time","_acc_min","_acc_max",
        "_internal_in","_internal_out","_internal_type"
    ], errors="ignore").sort_values(by=[col_data_transakcji]).reset_index(drop=True)

    meta = {
        "input_rows": len(df),
        "candidates_internal": len(internal),
        "pairs_removed": len(pairs),
        "rows_removed": len(to_drop),
        "output_rows": len(cleaned),
        "matching": {
            "uses_description": True,
            "phrase_in": phrase_in,
            "phrase_out": phrase_out,
            # "date_tolerance": date_tolerance,
            # "require_opposite_sign": require_opposite_sign
        }
    }

    return cleaned, report, meta


if __name__ == '__main__':
    main()
