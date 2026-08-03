# Cursor rules — kontekst i założenia (assets)

Ten plik to warstwa **dlaczego / założenia / granice**, której nie da się wiarygodnie odczytać z samego kodu.
Kod odpowiada na **jak**. Ten dokument — na **co obowiązuje** i **czego nie zmieniać bez decyzji**.

Agent Cursor: czytaj ten plik na początku pracy domenowej; po istotnej decyzji lub zmianie modelu zaktualizuj odpowiednią sekcję w tym samym PR/zmianie.

---

## Cel systemu

Śledzenie majątku (konta, depozyty, inwestycje, nieruchomości, złoto) + ROI inwestycji finansowanych z cash pools (mbank/revolut).

Źródła: Excel `a_config.xlsx` (Dropbox) — katalog portfela + ROI w jednym pliku; wyciągi bankowe; snapshoty parquet.

Arkusze `a_config.xlsx`:
- portfel: `assets`, `inventory`, `unit-price-evaluation`, `asset-evaluation` (+ ewentualne dynamiczne)
- ROI: `roi_def`, `roi_rules`, `roi_manual` (+ opcjonalnie `rules-non-active`)

---

## Słownik (nie mylić)

| Pojęcie | Znaczenie |
|--------|-----------|
| **cash pool** | Środki pieniężne na kontach ROR (`typ=cash_pool.ror`); runtime `pool_id` (mbank/revolut × PLN/EUR) |
| **investment.\*** | Aktywa nabyte / wyceniane jako inwestycje (w tym ROI `cash`, nieruchomości, złoto, obligacje…) |
| **`id=cash` / `assets.cash`** | Aktywo ROI (np. gotówka „wyprowadzona” do inwestycji), **nie** ewidencja gotówki bieżącej w portfelu |
| **`grupa`** | Agregacja raportowa (RAP1, wykres portfela) |
| **`typ`** | Klasa instrumentu; steruje m.in. `pool_id` i RAP2 |
| **`RODZAJ*`** | Ścieżka ewaluacji / importu (`mbank.*`, `assets.cash`, `assets.properties-wyceny`…) |
| **CAPEX** | Nakłady inwestycyjne (zakup) |
| **REVENUES** | Przychody (odsetki, dywidendy) — nie zmniejszenie pozycji |
| **OPEX** | Wydatki operacyjne (podatek, opłata) |
| **DIVESTMENT** | Zmniejszenie zaangażowania (częściowa lub pełna sprzedaż / zwrot kapitału); **nie** OPEX |
| **is_sold** | Brak otwartej ekspozycji (qty≈0 / data zamknięcia w manual) — **nie** tożsame z samym wierszem DIVESTMENT |

---

## Założenia domenowe (obowiązujące)

1. **Brak ewidencji gotówki bieżącej** — nie prowadzimy osobnego salda „portfel gotówkowy”; `typ=investment.cash`. Brak osobnej zakładki `cash` w `a_config.xlsx`.
2. **DIVESTMENT ≠ is_sold** — `DIVESTMENT` to kategoria cashflowu (także częściowa sprzedaż). `is_sold` ⇔ brak ekspozycji: brokerzy `qty≈0`; nieruchomości/cash — data zamknięcia z manual (`DIVESTMENT` jako marker pełnego wyjścia / lifecycle). Arkusz wycen / `operacja=sprzedane` nie ustawia flagi sprzedaży.
3. **Wspólny arkusz wycen NAV** — `asset-evaluation` (ex `properties-wyceny`) trzyma NAV dla nieruchomości **oraz** pozycji `assets.cash` (np. `cash`, `rocky-iv`). Snapshot i ROI terminal dla tych ID biorą stąd ostatnią wycenę ≤ data wyceny.
4. **Bez podwójnego liczenia** — przy rozwijaniu `assets.properties` / `properties-wyceny` / `asset-evaluation` **wykluczać** ID z wierszy katalogu `RODZAJ*=assets.cash`; te ID idą wyłącznie ścieżką `assets.cash`.
5. **Numer konta w regułach** — dopuszczalny NRB (cyfry) **albo** IBAN (np. `LU91…`).
6. **Arkusze generyczne w `a_config.xlsx`** (ex `assets_1`):
   - `inventory` (ex `zloto-monety-zakupy`) — ręczne: Data, `instrument`, waga, sztuki (+ opcjonalnie notatki); **bez** matchu bankowego
   - `unit-price-evaluation` (ex `zloto-monety-ceny`) — ceny jednostkowe per `instrument`
   - `asset-evaluation` (ex `properties-wyceny`) — NAV pozycji (nieruchomości, cash, rocky-iv, …)
   - **Usunięte:** `zloto-monety-wyceny` (wycena całego holdingu złota) — nie wraca; złoto MTM wyłącznie qty×cena
7. **Złoto ROI** (`asset_id=zloto-monety`):
   - **CAPEX** wyłącznie z `a_config` (`roi_rules` / `roi_manual`) via `allocate_catalog` — jak inne aktywa
   - **Inventory** z arkusza `inventory`; join CAPEX ↔ inventory **wyłącznie po dacie**
   - **Terminal / snapshot** = Σ sztuki × cena z `unit-price-evaluation`
   - **Brak / niejednoznaczne / niekompletne inventory** na datę CAPEX → **twardy błąd** (nie warning); CAPEX bez sztuk nie jest pomijany po cichu
8. **ROI cash a FX** — XIRR / ROI nominalny dla `cash` liczony w **walucie wyceny (EUR)**; bez przeliczania CAPEX/terminal FX w ROI. Przeliczenie na PLN jest w snapshocie portfela (`09 assets`), nie w warstwie ROI cash.
9. **Snapshoty** — raporty UI z `09 assets/*.parquet`; po zmianie logiki wyceny użytkownik regeneruje snapshot (przycisk w Raportach). Nie migrujemy historycznych parquetów bez prośby. Nowe snapshoty dla gotówki mają `id=cash` (nie `id=EUR`).
10. **Layout Dropbox `INWESTYCJE/`**:
    - `assets/` — `a_config.xlsx` (ex `assets_1` + `analyse_assets_config`), katalogi aktywów `investment.*`
    - `cash_pool/` — katalogi aktywów `cash_pool.*` (wyciągi ROR mBank/Revolut)
    - `download/pm|gm/` — źródło importu Revolut
    - Import wyciągów ROR trafia do `cash_pool/`; wyjątki w `assets/`: trading Revolut (`p_re_robo`), obligacje skarbowe (`obligacjeskarbowe`)
    - Migrator: `app/maintenance/migrate_to_a_config.py`

---

## Mapowanie `typ` (kanoniczne)

| Stare | Nowe |
|-------|------|
| `ror` | `cash_pool.ror` |
| `cash` | `investment.cash` |
| `depozyt` | `investment.depozyt` |
| `złoto-monety` | `investment.złoto-monety` |
| `udziały` | `investment.udziały` |
| `obligacje` | `investment.obligacje` |
| `property` | `investment.property` |

Migrator: `app/maintenance/migrate_assets_typ_prefix.py`.

---

## Import wyciągów (Revolut)

Źródła: `Dropbox/INWESTYCJE/download/pm` (`p_re`), `…/gm` (`g_re`). Przenoszenie do katalogów kont w Dropbox `cash_pool` (`p_re_*` / `g_re_*`).

| Prefiks nazwy pliku | Zachowanie |
|---------------------|------------|
| `account-statement_*` | Wyciąg konta → katalog waluty; data końca okresu z 3. segmentu nazwy (dopuszczalne dodatkowe sufiksy, np. `_1`) |
| stem = UUID (`xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`) | Depozyt → katalog waluty; inne nazwy bez `_` (np. `Eksport transakcji`) → pomijane |
| pusty plik account/deposit | Usuwany; w raporcie importu: „usunięty (pusty)” |
| `trading-account-statement_*` | Wyciąg brokerski Revolut (robo/trading) — osobna ścieżka (nie cash_pool) |
| `trading-pnl-statement_*` | Rachunek zysków i strat brokerskich (zrealizowane sprzedaże, dywidendy) |
| `consolidated-statement-v2_*`, `savings-statement_*` i inne nieznane | Pomijane — **nie** przerywają importu |

mBank: pliki `*_ *_ *.csv` (stem 22 znaki) z `~/Downloads` oraz luźne CSV w `assets/` → katalogi kont w `cash_pool/` po kluczu numeru rachunku.

Obligacje skarbowe (PKO BP): `StanRachunkuRejestrowego*.xls` oraz `HistoriaDyspozycji.xls` z `~/Downloads` → `assets/obligacjeskarbowe`. Przy przenoszeniu historia dostaje nazwę `{YYYY-MM-DD} {YYYY-MM-DD} HistoriaDyspozycji.xls` (min/max `DATA DYSPOZYCJI`). Jeśli w katalogu jest już plik zawierający wszystkie transakcje z nowego — nowy jest usuwany (pominięty); nadpisanie tej samej nazwy/zawartości nie jest błędem.

---

## Rachunek brokerski (Revolut robo + obligacje skarbowe PKO; wzorzec na XTB / Trade Republic / Degiro)

- To **nie** jest `cash_pool` ani pojedyncza inwestycja-lump z przelewu ROR — kontener pozycji instrumentów (+ gotówka robocza brokera).
- W katalogu: `RODZAJ*=BROKER`. **`roi_def` / reguły ROI nie są wymagane**.
  - Revolut: `id=p_re_robo`, `typ` → `investment.udziały`
  - Obligacje: `id=obligacjeskarbowe`, `typ=investment.obligacje`
- Dispatch snapshotu: `typ=investment.obligacje` → ewaluator obligacji; inaczej → Revolut trading.

### Revolut robo

- Źródła: `trading-account-statement_*` + `trading-pnl-statement_*`.
- Merge wielu plików: usuwać duplikaty; luki w okresach nazw → ostrzeżenie.
- Po wczytaniu blottera: SELL → `Quantity` ujemne; BUY → `Total Amount` ujemne; FX → `1/fx`.
- **Snapshot:** 1 wiersz — Σ koszt nabycia FIFO otwartych pozycji.
- **ROI:** per ticker (`p_re_robo:PRAR`); BUY → `CAPEX`; SELL → `DIVESTMENT`; DIVIDEND → `REVENUES`; FEE / TOP-UP poza XIRR; `is_sold` ⇔ qty≈0.
- Terminal otwartych = last trade price × qty; `is_sold` ⇔ qty == 0.
- Reconciliacja: Σ `CASH TOP-UP` vs `|To Robo portfolio|` na `revolut_eur` (tol. 0.01 EUR).

### Obligacje skarbowe (PKO BP)

- Źródła: `HistoriaDyspozycji` + `StanRachunkuRejestrowego` (MTM). Tylko `STATUS=zrealizowana`.
- Rejestry w historii dyspozycji:
  - **operacje na papierach** (qty/inventory): `dyspozycja zakupu`, `wykup papierów`, `dyspozycja przedterminowego wykupu` — przy imporcie `LICZBA OBLIGACJI` dla wykupów mnożona przez −1
  - **przepływy pieniężne** (źródło CF / eksport): m.in. `zakup papierów`, `wypłata przelewem`, `opłata za przedterminowy wykup`, naliczenia/podatek/odsetki (+ ręczne brakujące wypłaty) — do ROI idą tylko prawdziwe CF
  - **operacje na rachunku pieniężnym** (poza ROI per kod): `przedterminowy wykup`, `przelew z rachunku`
- `unit_price` liczony przy imporcie stanu: `WARTOŚĆ AKTUALNA / (DOSTĘPNA + ZABLOKOWANA)`.
- **Snapshot:** 1 wiersz — Σ `WARTOŚĆ AKTUALNA` z najnowszego stanu ≤ data wyceny (MTM, nie koszt zakupu).
- **ROI:** per kod; tylko CF: `zakup` → `CAPEX`; `wypłata` → `DIVESTMENT`; `opłata za przedterminowy wykup` → `OPEX`. **Poza ROI** (ekonomiczne, już w MTM): `naliczenie odsetek *`, `wykup - odsetki`, `podatek`, `odsetki`. `is_sold` ⇔ qty≈0.
- **Znaki kwot (obligacje, CF w 01 source):** `CAPEX` → ujemne; `OPEX` / `DIVESTMENT` → dodatnie.
- **TODO:** czy Revolut robo / klasyczne ROI (REVENUES +, OPEX −) powinny przejść na tę samą polarność, czy obligacje zostają wyjątkiem.
- Terminal otwartych = `WARTOŚĆ AKTUALNA` ze stanu; `is_sold` ⇔ open qty == 0.
- Usunięte: `RODZAJ*=obligacje_skarbowe_import` i wycena N wierszy z `KWOTA` zakupu.

- Lepsze MTM online (API) — osobna decyzja później.

---

## Preferencje pracy z kodem

- Python przez `uv run` z katalogu `app/`.
- Nie commitować bez prośby; nie pushować bez prośby.
- Nie dodawać zbędnych markdownów / refaktorów poza zakresem zadania.
- Testy obok zmiany reguły (unittest w `app/unit_testing/`).
- Streamlit: cache `@st.cache_data` — przy zmianie kształtu wyniku podbić `_schema` / `clear()`.
- Zakładka **Waliduj**: walidacja ROI (`roi_def`/`roi_rules`/`roi_manual`) + ewaluacja katalogu `assets` w `a_config.xlsx` (dry-run, bez zapisu snapshotu).
- **DATA_STEP** — jedyna warstwa cache i łańcucha zależności. Korzystamy **tylko z API wysokopoziomowego** — w praktyce wyłącznie z metod klasy `DataStep` (np. `init_steps`, `obtain`, `obtain_dependent`, `force_read_data`). Nie wywoływać prywatnych pól/metod (`_dependencies_stack`, `_dependencies`, …) i nie omijać DATA_STEP własnym cache. `roi/cache.py` to produkt domenowy (`10 roi_events`) na DATA_STEP, nie osobny system cache.
- Komunikacja z użytkownikiem: zwięźle, po polsku jeśli pyta po polsku.

---

## Non-goals (świadomie poza zakresem)

- Pełna speka algorytmów w tym pliku (to jest kod).
- Migracja wszystkich historycznych snapshotów przy każdej zmianie modelu.
- Osobny ledger gotówki bieżącej równoległy do cash pools.
- Osobna wycena całego holdingu złota (dawne `zloto-monety-wyceny`).
- Auto-migracja starego Excela inventory → nowy schemat bez prośby.
- FX w XIRR cash (osobna decyzja, jeśli kiedyś wspólny mianownik PLN z nieruchomościami).
- MTM online instrumentów brokerskich (yfinance/OpenFIGI itd.) — spike OK; produkcja odłożona; snapshot = koszt FIFO; ROI ticker = last price × qty.
- Klasyczne ROI katalogowe `p_re_robo` / `obligacjeskarbowe` z cash pool / `roi_def` (równolegle do ROI per instrument).
- Fee / TOP-UP / podatki / przelewy PKO w XIRR per instrument; rozbicie instrumentów w tabeli Raporty → Inwestycje.

---

## Jak aktualizować ten plik

Dopisz / popraw sekcję, gdy zmienia się:
- założenie domenowe,
- znaczenie pojęcia (`typ` / `grupa` / `pool`),
- reguła biznesowa (np. co oznacza sprzedaż),
- kanoniczna nazwa arkusza / kolumny / typu.

Nie zapisuj tu szczegółów implementacji (sygnatury, refaktory) — tylko decyzje i kontekst.
