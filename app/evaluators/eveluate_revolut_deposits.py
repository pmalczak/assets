"""
napisz kod w python z użyciem pandas w oparciu o następujące założenia.

kod służy do wyliczania wartości ulokowanych środków
dane wejściowe to transakcje na rachunku podtsaowym
nie mogę zrobić wyciągu z rachunku depozytowego, więc wartość depozytu wyznaczam
poprzez znalezienie transakcji  wypłaty i zwrotu z depozytu

input_df[RevolutFile.DESCRIPTION] == 'Depositing savings'
Kwota dla takiej transakcji (input_df[RevolutFile.AMOUNT]) ma wartość ujemną, bo reprezentuje wypływ z rachunku podstawowego.

input_df[RevolutFile.DESCRIPTION] == 'Withdrawal savings'
Kwota dla takiej transakcji (input_df[RevolutFile.AMOUNT]) ma wartość dodatnią, bo reprezentuje wpływ na rachunek podstawowy.

każda transakcja wpłaty jest traktowana jako osobny depozyt z datą depozytu
deposits[AssetsDef.EVALUATION_DATE] = input_df[RevolutFile.DATE]

wpłaty i wypłaty mogą następować w dowolnej kolejności
wypłaty powinny zmniejszać najstarszy depozyt aż do wyczerpania kwoty depozytu,
jeśli wypłata przekracza kwotę depozytu wybieramy kolejny najstarszy depozyt.

wyczerpanie ostatniej lokaty kończy algorytm

napisz kod procedury w oparciu o obecny kod, który realizuje tylko 'zakładanie' lokat


def _evaluate_deposits(df: pd.DataFrame, assets_file_row: pd.Series) -> list:
    cond = df[RevolutFile.DESCRIPTION] == 'Depositing savings'
    df = df[cond]

    result = []
    for i, row in df.iterrows():
        assets_row1 = AssetsDef.as_assets_row(assets_file_row)
        assets_row1[AssetsDef.VALUE] = - row[RevolutFile.AMOUNT]
        assets_row1[AssetsDef.EVALUATION_DATE] = row[RevolutFile.DATE]
        assets_row1[AssetsDef.GROUP] = GroupDomain.DEPOSIT
        assets_row1[AssetsDef.TYPE] = TypeDomain.DEPOSIT
        assets_row1[AssetsDef.DESCR] = 'lokata'
        result += [assets_row1]

    return result



Nie rób żadnych domyślnych założeń. jeśli trzeba podjąć decyzję to o nią zapytaj.
Napisz kod realizujący zarówno zakładanie jak też zamykanie depozytów


"""

from importers.assets.data_model import AssetsDef, GroupDomain, TypeDomain
from importers.revolut.account_data_model import RevolutAccountFile

import pandas as pd


def evaluate_revolut_deposits(df: pd.DataFrame, assets_file_row: pd.Series, product=None,
                              depositing_selector=None,
                              withdrowing_selector=None) -> list:
    """
    Buduje listę rekordów aktywów reprezentujących:
      - otwarcia lokat na podstawie transakcji 'Depositing savings'
      - zamykanie/zmniejszanie lokat na podstawie transakcji 'Withdrawal savings' (FIFO)

    Założenia (wynikające z treści zadania):
      - input_df[RevolutFile.DESCRIPTION] == 'Depositing savings'  => AMOUNT < 0 (wypływ z rachunku podstawowego)
        => wartość lokaty (aktywa) = -AMOUNT (liczba dodatnia)
      - input_df[RevolutFile.DESCRIPTION] == 'Withdrawal savings'  => AMOUNT > 0 (wpływ na rachunek podstawowy)
        => zmniejszamy najstarszy nierozliczony depozyt aż do wyczerpania
      - FIFO po dacie depozytu
      - wyczerpanie wszystkich lokat kończy algorytm (ew. nadwyżkę wypłat można obsłużyć inaczej – daj znać)

    Zwraca: listę wierszy (Series/Dict) przygotowanych przez AssetsDef.as_assets_row(assets_file_row).
    """
    # --- separacja wejść ---
    dep_mask = df[RevolutAccountFile.DESCRIPTION] == depositing_selector
    wdr_mask = df[RevolutAccountFile.DESCRIPTION] == withdrowing_selector

    deposits_df = df.loc[dep_mask].copy()
    withdrawals_df = df.loc[wdr_mask].copy()

    # Bez założeń dot. sortowania wejścia – jawnie sortujemy po dacie
    deposits_df = deposits_df.sort_values(by=[RevolutAccountFile.DATE, RevolutAccountFile.AMOUNT], kind="stable")
    withdrawals_df = withdrawals_df.sort_values(by=[RevolutAccountFile.DATE, RevolutAccountFile.AMOUNT], kind="stable")

    result = []

    # --- 1) Otwieranie lokat (każda wpłata = osobny depozyt) ---
    # Jednocześnie budujemy kolejkę "lotów" depozytów do późniejszego rozliczania wypłat (FIFO).
    # Każdy lot: słownik z pozostającą kwotą i datą założenia (do opisu).
    lots = []

    for _, row in deposits_df.iterrows():
        amt = row[RevolutAccountFile.AMOUNT]
        if amt >= 0:
            raise ValueError

        deposit_value = -amt  # dodatnia wartość aktywa
        # wiersz aktywa dla OTWARCIA
        assets_row_open = AssetsDef.as_assets_row(assets_file_row)
        assets_row_open[AssetsDef.VALUE] = deposit_value
        assets_row_open[AssetsDef.EVALUATION_DATE] = row[RevolutAccountFile.DATE]
        assets_row_open[AssetsDef.GROUP] = GroupDomain.DEPOSIT
        assets_row_open[AssetsDef.TYPE] = TypeDomain.DEPOSIT
        assets_row_open[AssetsDef.DESCR] = f'{product} (otwarcie)'
        result.append(assets_row_open)

        # dodaj "lot" do kolejki FIFO (pozostała kwota = pełna wartość lokaty)
        lots.append({
            "remaining": float(deposit_value),
            "opened_on": row[RevolutAccountFile.DATE],
        })

    # --- 2) Zamykanie/zmniejszanie lokat wg wypłat, FIFO ---
    for _, row in withdrawals_df.iterrows():
        amt = row[RevolutAccountFile.AMOUNT]
        if amt <= 0:
            raise ValueError

        remaining_to_apply = float(amt)

        # Schodzimy po lotach od najstarszego
        lot_idx = 0
        while remaining_to_apply > 0 and lot_idx < len(lots):
            lot = lots[lot_idx]
            if lot["remaining"] <= 0:
                lot_idx += 1
                continue

            applied = min(remaining_to_apply, lot["remaining"])

            # wiersz aktywa dla ZAMKNIĘCIA (zmniejszamy aktywo, więc wartość ujemna)
            assets_row_close = AssetsDef.as_assets_row(assets_file_row)
            assets_row_close[AssetsDef.VALUE] = -applied
            assets_row_close[AssetsDef.EVALUATION_DATE] = row[RevolutAccountFile.DATE]
            assets_row_close[AssetsDef.GROUP] = GroupDomain.DEPOSIT
            assets_row_close[AssetsDef.TYPE] = TypeDomain.DEPOSIT
            # opiszemy z referencją do daty otwarcia lota
            assets_row_close[AssetsDef.DESCR] = f"{product} (zamknięcie FIFO z {lot['opened_on']})"
            result.append(assets_row_close)

            # aktualizacja stanu
            lot["remaining"] -= applied
            remaining_to_apply -= applied

            # jeśli lot wyzerowany – przechodzimy do kolejnego
            if lot["remaining"] <= 1e-9:
                lot["remaining"] = 0.0
                lot_idx += 1

        # Jeśli zabrakło lotów, kończymy zgodnie z wymaganiem (ignorujemy nadwyżkę wypłaty).
        # Jeżeli wolisz, abym tu zgłaszał błąd/ostrzeżenie – daj znać.

    return result
