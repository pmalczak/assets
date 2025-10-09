# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

import pandas as pd


def deduplicate_records(df1, df2, date_src_col, key_cols):
    date_col = '_data_'

    # --- przygotowanie ---
    df1 = df1.copy()
    df2 = df2.copy()
    df1[date_col] = pd.to_datetime(df1[date_src_col])
    df2[date_col] = pd.to_datetime(df2[date_src_col])

    # zakresy dat
    min1, max1 = df1[date_col].min(), df1[date_col].max()
    min2, max2 = df2[date_col].min(), df2[date_col].max()

    # wyznacz nakładający się zakres (jeśli istnieje)
    overlap_start = max(min1, min2)
    overlap_end = min(max1, max2)

    # jeśli brak nakładki, po prostu sklej i wyjdź
    if overlap_start > overlap_end:
        merged = pd.concat([df1, df2], ignore_index=True)

    else:
        merged = deduplicate_overlapped_records(df1, df2, date_col, key_cols, overlap_start, overlap_end)

    merged = merged.sort_values(by=[date_col]).reset_index(drop=True)
    merged = merged.drop(columns=[date_col])
    return merged


def deduplicate_overlapped_records(df1, df2, date_col, key_cols, overlap_start, overlap_end):
    m1_overlap = df1[date_col].between(overlap_start, overlap_end)
    m2_overlap = df2[date_col].between(overlap_start, overlap_end)

    df1_nonover, df2_nonover = df1[~m1_overlap], df2[~m2_overlap]
    df1_overlap, df2_overlap = df1[m1_overlap], df2[m2_overlap]

    assert len(df1) == len(df1_nonover) + len(df1_overlap)
    assert len(df2) == len(df2_nonover) + len(df2_overlap)

    overlap_combined = pd.concat([df1_overlap, df2_overlap], ignore_index=True)

    removed_mask = overlap_combined.duplicated(subset=key_cols, keep='last')
    dup_keys = overlap_combined.loc[:, key_cols].astype(str).agg('|'.join, axis=1)
    duplicates_report = overlap_combined.loc[removed_mask].copy()
    duplicates_report.loc[:, 'duplicate_key'] = dup_keys.loc[removed_mask]

    deduped_overlap = overlap_combined.drop_duplicates(subset=key_cols, keep='last')
    merged = pd.concat([df1_nonover, df2_nonover, deduped_overlap], ignore_index=True)

    if (len(overlap_combined) > 0
            and len(duplicates_report) == 0
            and (overlap_end - overlap_start) > pd.Timedelta(days=2)):
        raise ValueError

    if len(duplicates_report) > 0:
        print(f"{overlap_start.date()} — {overlap_end.date()} Usunięto {len(duplicates_report)} duplikatów")

    return merged
