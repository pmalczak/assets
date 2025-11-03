import pandas as pd
from io import StringIO

from importers.revolut.data_model import RevolutFile, RevolutFileState


def read_revolut_transaction_file(file):
    # --- 1) Wczytaj pierwszą kolumnę z XLSX jako tekst ---
    s = (
        pd.read_excel(
            file,
            header=None,
            usecols=[0],
            dtype=str,
            engine="openpyxl",
        )
        .iloc[:, 0]
        .dropna()
        .astype(str)
    )

    # --- 2) Odkręć mojibake linia po linii ---
    fixed_lines = s.map(unmojibake)
    text_block = "\n".join(fixed_lines)

    # --- 3) Wykryj separator, biorąc taki, który daje najwięcej kolumn (>1) ---
    best_df, best_cols = None, 0
    for sep in (",", ";", "\t", "|"):
        try:
            # quoting=3 -> QUOTE_NONE (szybsze); jak masz cudzysłowy w danych, usuń ten parametr
            df_try = pd.read_csv(StringIO(text_block), sep=sep, dtype=str)
            if df_try.shape[1] > best_cols:
                best_cols = df_try.shape[1]
                best_df = df_try
        except Exception:
            pass

    if best_df is None or best_df.shape[1] == 1:
        raise ValueError("Nie udało się uzyskać wielokolumnowej tabeli – sprawdź separator i źródło.")

    df = best_df

    df[RevolutFile.STATE] = df[RevolutFile.STATE].replace({'ZAKOCZONO':RevolutFileState.CLOSED})
    df[RevolutFile.KIND] = df[RevolutFile.KIND].replace({'Opata': 'Opłata',
                                                         'Patno kart': 'Płatność kartą'})
    df[RevolutFile.PRODUCT] = df[RevolutFile.PRODUCT].replace({'Biece':'Bieżące'})

    for col in (RevolutFile.AMOUNT, RevolutFile.FEE, RevolutFile.BALANCE):
        df[col] = df[col].astype('float')

    print(df)

    return df


def unmojibake(s: str) -> str:
    """
    Próbuje odwrócić klasyczne mojibake: UTF-8 błędnie zdekodowane jako single-byte.
    Testuje kilka popularnych kodowań ('cp1252', 'latin1', 'cp1250').
    Jeśli wszystkie zawiodą – zwraca oryginał.
    """
    for enc in ("cp1252", "latin1", "cp1250"):
        try:
            return s.encode(enc).decode("utf-8")
        except UnicodeError:
            continue
    # Ostateczny fallback – miękko zastępuj nieobsługiwalne znaki
    try:
        return s.encode("latin1", errors="ignore").decode("utf-8", errors="ignore")
    except Exception:
        return s
