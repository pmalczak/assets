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
| **DIVESTMENT** | Cashflow wyjścia kapitału; **nie** OPEX. Dla `investment.property` = sprzedaż (zamknięcie). Dla brokerów/obligacji/depozytów może być częściowe zmniejszenie pozycji |
| **is_sold** | Brak otwartej ekspozycji: `investment.property` ⇔ jest DIVESTMENT ≤ data wyceny; brokerzy `qty≈0`; cash — data zamknięcia z manual |

---

## Założenia domenowe (obowiązujące)

1. **Brak ewidencji gotówki bieżącej** — nie prowadzimy osobnego salda „portfel gotówkowy”; `typ=investment.cash`. Brak osobnej zakładki `cash` w `a_config.xlsx`.
2. **DIVESTMENT a is_sold** — zależy od `typ`:
   - **`investment.property`**: DIVESTMENT (bank lub manual) **=** sprzedaż / `is_sold` (nieruchomość nie ma częściowego „zmniejszenia zaangażowania” jak obligacje)
   - **brokerzy / obligacje / depozyty**: DIVESTMENT może być częściowy; `is_sold` ⇔ `qty≈0`
   - **`investment.cash`**: `is_sold` z daty zamknięcia w `roi_manual` (DIVESTMENT/CLOSING)
   - Arkusz wycen / `operacja=sprzedane` nie ustawia flagi sprzedaży.
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
| `savings-statement_{od}_{do}_…` | Wyciąg depozytu (PL) → katalog waluty; **waluta z treści kwot** (`PLN` / `€`), nie z `kod1` w nazwie; nakładające się okresy → dedupe; **luka w pokryciu okresów → twardy błąd** |
| stem = UUID (`xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`) | Legacy depozyt (EN) → katalog waluty; inne nazwy bez `_` → pomijane |
| `Eksport transakcji.csv` | **Trade Republic** — przenoszone **przed** Revolut PM (osobna ścieżka, nie skip Revolut) |
| pusty plik account/deposit/savings | Usuwany; w raporcie importu: „usunięty (pusty)” |
| `trading-account-statement_*` | Wyciąg brokerski Revolut (robo/trading) — osobna ścieżka (nie cash_pool) |
| `trading-pnl-statement_*` | Rachunek zysków i strat brokerskich (zrealizowane sprzedaże, dywidendy) |
| `consolidated-statement-v2_*` i inne nieznane | Pomijane — **nie** przerywają importu |

### ROI depozytów Revolut (savings)

- `asset_id` = katalog konta: `p_re_eur` / `p_re_pln` / `g_re_eur` / `g_re_pln` (osobno od ROR cash pool w sensie produktu ROI).
- CF z `Opis`: `Depozyt` → `CAPEX` (`−abs`); `Wypłata` → `DIVESTMENT` (`+abs`). **`Oprocentowanie brutto` poza CF / XIRR** (jak odsetki w obligacjach) — efekt w `Saldo` / terminalu.
- Terminal / snapshot NAV = ostatnie `Saldo` ≤ data wyceny.
- Zobowiązanie podatkowe Belka 19%: osobne `asset_id` `{deposit_id}_zobowiazanie_podatkowe_{Y}` — OPEX `−0.19×` oprocentowania brutto tylko dla odsetek z roku `Y` (rok daty wyceny); w snapshocie wartość ujemna = zaległość YTD.

mBank: pliki `*_ *_ *.csv` (stem 22 znaki) z `~/Downloads` oraz luźne CSV w `assets/` → katalogi kont w `cash_pool/` po kluczu numeru rachunku.

Trade Republic (PM): `Eksport transakcji.csv` z `download/pm` → `assets/p_traderepublic/eksport-transakcji_{od}_{do}.csv` (min/max kolumny `date`). Merge wielu plików: **luka okresów → twardy błąd**; overlap → dedupe po `transaction_id`. W katalogu: `id=p_traderepublic`, `RODZAJ*=BROKER`, `typ=investment.udziały`, `waluta=PLN`; bez `roi_def`. Snapshot na start: 1 wiersz NAV=0 (mapowanie BUY/SELL / ROI per instrument — osobna decyzja).

Obligacje skarbowe (PKO BP): `StanRachunkuRejestrowego*.xls` oraz `HistoriaDyspozycji.xls` z `~/Downloads` → `assets/obligacjeskarbowe`. Przy przenoszeniu historia dostaje nazwę `{YYYY-MM-DD} {YYYY-MM-DD} HistoriaDyspozycji.xls` (min/max `DATA DYSPOZYCJI`). Jeśli w katalogu jest już plik zawierający wszystkie transakcje z nowego — nowy jest usuwany (pominięty); nadpisanie tej samej nazwy/zawartości nie jest błędem.

---

## Rachunek brokerski (Revolut robo + obligacje skarbowe PKO + Trade Republic; wzorzec na XTB / Degiro)

- To **nie** jest `cash_pool` ani pojedyncza inwestycja-lump z przelewu ROR — kontener pozycji instrumentów (+ gotówka robocza brokera).
- W katalogu: `RODZAJ*=BROKER`. **`roi_def` / reguły ROI nie są wymagane**.
  - Revolut: `id=p_re_robo`, `typ` → `investment.udziały`
  - Obligacje: `id=obligacjeskarbowe`, `typ=investment.obligacje`
  - Trade Republic: `id=p_traderepublic`, `typ` → `investment.udziały`
- Dispatch snapshotu: `typ=investment.obligacje` → ewaluator obligacji; `id=p_traderepublic` → Trade Republic; inaczej → Revolut trading.

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
- Globalny filtr pozycji (sidebar): Niesprzedane / Sprzedane / Wszystkie — tabele ROI wg `is_sold`. Preferencja w `_ui/sold_filter.txt`. Snapshoty i tak pomijają `VALUE=0`.
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
