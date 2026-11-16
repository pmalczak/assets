# -*- coding: utf-8 -*-
"""Parser nowego wyciągu konta Revolut (PDF multi-walutowy) → schemat CSV account-statement.

Krok 1 (PDF→CSV); krok 2 = istniejący import CSV / split Waluta. Bez wiringu w move_downloaded.
Wymaga pdfplumber (Linux + Windows).
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pdfplumber

from importers.revolut.account_data_model import RevolutAccountFile, RevolutOperationType
from importers.revolut.revolut_file_state import RevolutFileState

_MONTHS_PL = {
    "sty": 1,
    "lut": 2,
    "mar": 3,
    "kwi": 4,
    "maj": 5,
    "cze": 6,
    "lip": 7,
    "sie": 8,
    "wrz": 9,
    "paź": 10,
    "paz": 10,
    "lis": 11,
    "gru": 12,
}

_DATE_LINE_RE = re.compile(
    r"^(?P<day>\d{1,2})\s+(?P<mon>[A-Za-ząćęłńóśźżĄĆĘŁŃÓŚŹŻ]{3})\s+(?P<year>\d{4})\b",
    re.UNICODE,
)
_CURRENCY_HEADER_RE = re.compile(r"Wyciąg\s+(PLN|EUR)\b", re.IGNORECASE)
_CSV_COLUMNS = [
    RevolutAccountFile.KIND,
    RevolutAccountFile.PRODUCT,
    RevolutAccountFile.INIT_DATE,
    RevolutAccountFile.DATE,
    RevolutAccountFile.DESCRIPTION,
    RevolutAccountFile.AMOUNT,
    RevolutAccountFile.FEE,
    RevolutAccountFile.CURRENCY,
    RevolutAccountFile.STATE,
    RevolutAccountFile.BALANCE,
]

# Prefiks generacji w nazwie PDF: YYYY_MM_DD_account-statement_…
_PDF_PREFIX_RE = re.compile(
    r"^(?:\d{4}_\d{2}_\d{2}_)?(?P<stem>account-statement_.+)$",
    re.IGNORECASE,
)


def parse_revolut_account_statement_pdf(path: Path | str) -> pd.DataFrame:
    """Zwraca DataFrame w schemacie surowego CSV Revolut (bez ref_date), obie waluty."""
    path = Path(path)
    rows: list[dict] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            rows.extend(_parse_page(page))
    if not rows:
        raise ValueError(f"Brak transakcji w wyciągu Revolut PDF: {path.name}")
    return pd.DataFrame(rows, columns=_CSV_COLUMNS)


def write_revolut_account_statement_csv(df: pd.DataFrame, out_path: Path | str) -> Path:
    """Zapisuje CSV gotowy do istniejącego importu / split Waluta."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    export = df.loc[:, _CSV_COLUMNS].copy()
    export.to_csv(out_path, index=False)
    return out_path


def csv_name_from_pdf(pdf_path: Path | str) -> str:
    """`2026_11_01_account-statement_…_092cc2.pdf` → `account-statement_…_092cc2.csv`."""
    stem = Path(pdf_path).stem
    m = _PDF_PREFIX_RE.match(stem)
    if not m:
        raise ValueError(f"Nieoczekiwana nazwa wyciągu Revolut PDF: {Path(pdf_path).name}")
    return f"{m.group('stem')}.csv"


def convert_revolut_account_statement_pdf(
    pdf_path: Path | str,
    out_dir: Path | str | None = None,
) -> Path:
    """PDF → CSV obok pliku (lub w out_dir)."""
    pdf_path = Path(pdf_path)
    out_dir = Path(out_dir) if out_dir is not None else pdf_path.parent
    out_path = out_dir / csv_name_from_pdf(pdf_path)
    df = parse_revolut_account_statement_pdf(pdf_path)
    return write_revolut_account_statement_csv(df, out_path)


def _parse_page(page) -> list[dict]:
    words = page.extract_words() or []
    if not words:
        return []

    currency = _page_currency(words)
    cols = _column_bounds(words)
    if currency is None or cols is None:
        return []

    lines = _cluster_lines(words)
    in_tx = False
    records: list[dict] = []
    current: dict | None = None

    for line in lines:
        text = _line_text(line)
        if not text:
            continue
        if text.startswith("Zgłoś kradzież") or "Revolut Bank UAB to bank" in text:
            break
        if text.startswith("Data ") and "Opis" in text and "Wydatki" in text:
            in_tx = True
            continue
        if not in_tx:
            continue
        if text.startswith("Transakcje na koncie"):
            continue

        date_iso = _parse_date_prefix(text)
        if date_iso is not None:
            if current is not None:
                records.append(_finalize_record(current, currency))
            current = _start_record(line, cols, date_iso)
            continue

        if current is None:
            continue

        # Orphan „PLN” / counter-FX — pomijamy (nie tworzą rekordu).
        if _is_fx_or_currency_continuation(line, cols):
            continue

        lower = text.lower()
        if lower.startswith("karta:"):
            current["has_card"] = True
            continue
        if lower.startswith(("do:", "od:", "dane referencyjne:")):
            continue

        # Opis kontynuowany rzadko; nie dokładamy do tytułu (CSV ma jedną linię Opis).
        continue

    if current is not None:
        records.append(_finalize_record(current, currency))
    return records


def _page_currency(words: list[dict]) -> str | None:
    # Nagłówek „Wyciąg EUR/PLN” jest na górze strony.
    top_words = [w for w in words if w["top"] < 120]
    text = " ".join(w["text"] for w in sorted(top_words, key=lambda w: (w["top"], w["x0"])))
    m = _CURRENCY_HEADER_RE.search(text)
    return m.group(1).upper() if m else None


def _column_bounds(words: list[dict]) -> dict[str, float] | None:
    """Granice x kolumn z nagłówka Data / Opis / Wydatki / Wpływy / Saldo."""
    for line in _cluster_lines(words):
        by_text = {w["text"]: w["x0"] for w in line}
        if {"Data", "Opis", "Wydatki", "Wpływy", "Saldo"} <= set(by_text):
            wydatki = by_text["Wydatki"]
            wplywy = by_text["Wpływy"]
            saldo = by_text["Saldo"]
            return {
                "opis": by_text["Opis"],
                "wydatki": wydatki,
                "wplywy": wplywy,
                # Saldo bywa nieco na lewo od nagłówka Saldo — środek między Wpływy a Saldo.
                "saldo": (wplywy + saldo) / 2.0,
            }
    return None


def _cluster_lines(words: list[dict], y_tol: float = 3.0) -> list[list[dict]]:
    lines: list[list[dict]] = []
    for w in sorted(words, key=lambda x: (x["top"], x["x0"])):
        if not lines or abs(w["top"] - lines[-1][0]["top"]) > y_tol:
            lines.append([w])
        else:
            lines[-1].append(w)
    return lines


def _line_text(line: list[dict]) -> str:
    return " ".join(w["text"] for w in line).strip()


def _parse_date_prefix(text: str) -> str | None:
    m = _DATE_LINE_RE.match(text.strip())
    if not m:
        return None
    mon = _MONTHS_PL.get(m.group("mon").lower())
    if mon is None:
        return None
    return f"{int(m.group('year')):04d}-{mon:02d}-{int(m.group('day')):02d}"


def _start_record(line: list[dict], cols: dict[str, float], date_iso: str) -> dict:
    desc_words = [w["text"] for w in line if cols["opis"] - 1 <= w["x0"] < cols["wydatki"]]
    # Data zajmuje lewą kolumnę — pomiń day/mon/year już sparowane.
    # Opis zaczyna się od Opis.x0; words w zakresie opis.
    description = " ".join(desc_words).strip()
    wydatki = _amount_in_band(line, cols["wydatki"], cols["wplywy"])
    wplywy = _amount_in_band(line, cols["wplywy"], cols["saldo"])
    saldo = _amount_in_band(line, cols["saldo"], 1e9)
    if wydatki is not None and wplywy is not None:
        raise ValueError(f"Transakcja z Wydatkami i Wpływami naraz: {description}")
    if wydatki is None and wplywy is None:
        raise ValueError(f"Brak kwoty (Wydatki/Wpływy) dla: {description}")
    if saldo is None:
        raise ValueError(f"Brak salda dla: {description}")
    signed = -abs(wydatki) if wydatki is not None else abs(wplywy)
    return {
        "date": date_iso,
        "description": description,
        "signed_amount": signed,
        "balance": saldo,
        "has_card": False,
    }


def _amount_in_band(line: list[dict], x0: float, x1: float) -> float | None:
    tokens = [w["text"] for w in line if x0 - 0.5 <= w["x0"] < x1 - 0.5]
    if not tokens:
        return None
    raw = " ".join(tokens)
    return _parse_money(raw)


def _parse_money(raw: str) -> float | None:
    s = raw.replace("€", "").replace("PLN", "").replace(" ", "").strip()
    if not s:
        return None
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError as exc:
        raise ValueError(f"Nieparsowalna kwota w PDF: {raw!r}") from exc


def _is_fx_or_currency_continuation(line: list[dict], cols: dict[str, float]) -> bool:
    text = _line_text(line)
    if text in {"PLN", "€", "EUR"}:
        return True
    # Counter-amount FX: same band as Wydatki/Wpływy, no date / opis title.
    if _DATE_LINE_RE.match(text):
        return False
    # Same currency suffix as counter-leg (€ on PLN page or PLN on EUR page).
    if "€" in text or re.search(r"\bPLN\b", text):
        # Only digits + currency in money columns → continuation.
        if all(w["x0"] >= cols["wydatki"] - 0.5 for w in line):
            return True
    return False


def _finalize_record(current: dict, currency: str) -> dict:
    description = current["description"]
    signed = float(current["signed_amount"])
    kind = _infer_kind(description, current["has_card"])
    amount = signed
    fee = 0.0
    if kind == "Opłata":
        fee = abs(signed)
        amount = 0.0
    ts = f"{current['date']} 00:00:00"
    return {
        RevolutAccountFile.KIND: kind,
        RevolutAccountFile.PRODUCT: "Bieżące",
        RevolutAccountFile.INIT_DATE: ts,
        RevolutAccountFile.DATE: ts,
        RevolutAccountFile.DESCRIPTION: description,
        RevolutAccountFile.AMOUNT: amount,
        RevolutAccountFile.FEE: fee,
        RevolutAccountFile.CURRENCY: currency,
        RevolutAccountFile.STATE: RevolutFileState.CLOSED,
        RevolutAccountFile.BALANCE: float(current["balance"]),
    }


def _infer_kind(description: str, has_card: bool) -> str:
    if has_card:
        return RevolutOperationType.CARD_PAYMENT
    if description.startswith("Wymiana"):
        return "Wymiana"
    if description.startswith("Opłata"):
        return "Opłata"
    if description.startswith("Płatność od"):
        return "Zasilenie"
    return RevolutOperationType.PRZELEW
