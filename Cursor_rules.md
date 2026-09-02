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
| **`grupa`** | Agregacja raportowa (RAP1, wykres wartości) — nie mylić z **portfelem** |
| **portfel** | Przypisanie aktywa (nie nowe ID, nie `grupa`): `0 OGÓLNY` / `1 REVOLUT-ROBO` / `2 G-MOMENTUM`. Dotyczy `investment.*` **i** `cash_pool.*`. **`0 OGÓLNY`** = domyślny (w tym cały cash pool i każde nowe aktywo). Nie mylić z plikiem `a_config.xlsx` („katalog aktywów”). |
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
   - **`investment.property`**: DIVESTMENT (bank lub manual) **=** sprzedaż / `is_sold` (nieruchomość nie ma częściowego „zmniejszenia zaangażowania” jak obligacje). ID w ROI.Katalog (`roi_def`, np. `horbaczewskiego`) **nie musi** być wierszem w arkuszu `assets` (tam rodzic `id=properties`, `RODZAJ*=assets.properties`); `is_sold` z DIVESTMENT w CF, nawet jednokrotnego.
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
    - Wyciąg, którego okres z nazwy **całkowicie zawiera się** w innym pliku tego samego rodzaju (to samo konto mBank / ten sam prefix Revolut `account-statement` lub `savings-statement`) jest zbędny — `maintenance/prune_contained_statements.py` (domyślnie dry-run; `--delete` kasuje). Równe okresy: zostaje jeden plik. UUID depozytów (bez dat w nazwie) poza tą regułą. Ten sam skrypt raportuje **luki** między pozostałymi okresami (next.start > prev.end + 1 dzień), np. `…_200101_200228` i `…_200315_200630`.
    - Migrator: `app/maintenance/migrate_to_a_config.py`
11. **Portfel** — każde `investment.*` i `cash_pool.*` ma dokładnie jeden: `0 OGÓLNY` (default, w tym cash pool), `1 REVOLUT-ROBO` albo `2 G-MOMENTUM`. Nie jest to `grupa` ani osobny wiersz katalogu. RAP 1 = portfel × grupa; RAP 2 = portfel × typ (+ `RAZEM-PLN` = `wartość-pln_eur` + `wartość-pln_pln`).

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

### ROI lokat mBank

- Osobna venue ROI (nie `roi_def`).
- Snapshot **Wartość aktywów**: 1 wiersz `investment.depozyt` na konto mBank (`id` = konto ROR); `VALUE` = Σ kapitał otwartych lokat (−CAPEX). Zamknięte lokaty nie wchodzą. Szczegóły per NR są w zakładce ROI.
- Klucz ROI: `{account_id}:{NR 15 cyfr}` z `#Tytuł` (`\bNR \d{15}\b`). `#Opis operacji` mapuje CF.
- `OTW. LOKATY NR …` (przelew wychodzący) → `CAPEX`; `ZERWANIE` / `WYGAŚNIĘCIE` → `DIVESTMENT` (sam kapitał, **pełne zamknięcie**); `ODSETKI LOKAT TERMINOWYCH` → `REVENUES`; `PODATEK OD ODSETEK…` **z NR** → `OPEX`. Podatek ROR bez NR i przelewy bez `OTW. LOKATY` poza ROI.
- Terminal otwartej = −Σ CAPEX (kapitał; odsetki już na ROR). Po DIVESTMENT: `is_sold`, terminal 0. `roi_nominal` = odsetki netto (REVENUES+OPEX).

Trade Republic (PM): `Eksport transakcji.csv` z `download/pm` → `assets/p_traderepublic/eksport-transakcji_{od}_{do}.csv` (min/max kolumny `date`). Merge wielu plików: **luka okresów → twardy błąd**; overlap → dedupe po `transaction_id`. W katalogu: `id=p_traderepublic`, `RODZAJ*=BROKER`, `typ=investment.udziały`, `waluta=PLN`; bez `roi_def`. Snapshot na start: 1 wiersz NAV=0 (mapowanie BUY/SELL / ROI per instrument — osobna decyzja).

Obligacje skarbowe (PKO BP): `StanRachunkuRejestrowego*.xls` oraz `HistoriaDyspozycji.xls` z `~/Downloads` → `assets/obligacjeskarbowe`. Przy przenoszeniu historia dostaje nazwę `{YYYY-MM-DD} {YYYY-MM-DD} HistoriaDyspozycji.xls` (min/max `DATA DYSPOZYCJI`). Jeśli w katalogu jest już plik zawierający wszystkie transakcje z nowego — nowy jest usuwany (pominięty); nadpisanie tej samej nazwy/zawartości nie jest błędem.

---

## Rachunek brokerski (Revolut robo + obligacje skarbowe PKO + Trade Republic + DEGIRO + XTB)

- To **nie** jest `cash_pool` ani pojedyncza inwestycja-lump z przelewu ROR — kontener pozycji instrumentów (+ gotówka robocza brokera).
- W katalogu: `RODZAJ*=BROKER`. **`roi_def` / reguły ROI nie są wymagane**. DEGIRO używa `id=p_degiro`, `typ=investment.udziały`, `waluta=EUR`.
  - Revolut: `id=p_re_robo`, `typ` → `investment.udziały`
  - Obligacje: `id=obligacjeskarbowe`, `typ=investment.obligacje`
  - Trade Republic: `id=p_traderepublic`, `typ` → `investment.udziały`
  - XTB: `id=p_xtb`, `typ` → `investment.udziały`, `waluta=PLN` (zgodnie z rachunkiem `55260027`; eksport `PLN_…`)
- Dispatch snapshotu: `typ=investment.obligacje` → ewaluator obligacji; pozostali brokerzy udziałowi przez rejestr `BROKER_SNAPSHOT_EVALUATORS` (`p_traderepublic`, `p_degiro`, `p_xtb`, `p_re_robo`). Nieznane `id` **nie** spadają na Revolut — warning i brak wiersza.
- Snapshot brokera udziałowego (DEGIRO / XTB / Revolut robo): **1 wiersz = wartość pozycji + gotówka robocza**. Wymuszenie: `BrokerHoldings(positions_value, cash_value)` + `BrokerSnapshotEvaluator`; nowy broker = podklasa + wpis w rejestrze. Dziedziczenie bez rejestru nic nie daje. Obligacje PKO są poza tym kontraktem (MTM papierów). Trade Republic v1: wyjątek — NAV=0 (instrumenty niezmapowane).
- Docelowy przepływ architektoniczny:

```text
DEGIRO export --> DegiroAdapter --+
                                  +--> Normalized Portfolio --> Performance
XTB export -----> XtbAdapter -----+             |
                                                |
Market Data --> GMS Ranking --> Target --------+
                                                |
                                                +--> Rebalancing
                                                     BUY / SELL
```

### Revolut robo

- Źródła: `trading-account-statement_*` + `trading-pnl-statement_*`.
- Merge wielu plików: usuwać duplikaty; luki w okresach nazw → ostrzeżenie.
- Po wczytaniu blottera: SELL → `Quantity` ujemne; BUY → `Total Amount` ujemne; FX → `1/fx`.
- **Snapshot:** 1 wiersz — Σ koszt nabycia FIFO otwartych pozycji **+ gotówka robocza z blottera** (TOP-UP / SELL / DIVIDEND − BUY / FEE). Sama gotówka (wpłata bez kupna) też daje wiersz. Zakładka ROI per ticker **bez** gotówki w XIRR (TOP-UP/FEE poza XIRR jak dotychczas).
- **ROI:** per ticker (`p_re_robo:PRAR`); BUY → `CAPEX`; SELL → `DIVESTMENT`; DIVIDEND → `REVENUES`; FEE / TOP-UP poza XIRR; `is_sold` ⇔ qty≈0.
- Terminal otwartych = last trade price × qty; `is_sold` ⇔ qty == 0.
- Reconciliacja: Σ `CASH TOP-UP` vs `|To Robo portfolio|` na `revolut_eur` (tol. 0.01 EUR).

### DEGIRO

- W katalogu: `id=p_degiro`, `RODZAJ*=BROKER`, `typ=investment.udziały`, `waluta=EUR`; bez `roi_def` / `roi_rules`.
- Źródła: pakiet `Portfolio.csv`, `Transactions.csv`, `Account.csv` z `~/Downloads`; import pakietowy do `assets/p_degiro/`.
- Import wymaga kompletu 3 plików. Okres pakietu = `min(Data)..max(Data)` z pierwszej kolumny `Data` w `Account.csv` (data księgowania); te same daty obowiązują wszystkie trzy pliki.
- Nazwy docelowe: `portfolio_{od}_{do}.csv`, `transactions_{od}_{do}.csv`, `account_{od}_{do}.csv`.
- Format eksportu PL: separator CSV `,`, liczby z przecinkiem dziesiętnym w cudzysłowie; w `Account.csv` są dwie kolumny `Data` i puste nagłówki walut — importer nadaje nazwy techniczne (`booking_date`, `value_date`, `change_currency`, `balance_currency`).
- Przy przenoszeniu: istniejący identyczny/obejmujący pakiet → skip + usunięcie incoming; ten sam okres z inną treścią → twardy konflikt.
- Przy odczycie wielu pakietów: `Transactions` dedupe po `Identyfikator zlecenia` + polach transakcji; `Account` dedupe po pełnym kluczu księgowania. Overlap okresów jest OK; luka okresów → warning w v1.
- `Portfolio.csv` nie jest ledgerem; to snapshot na datę. Okres pakietu pochodzi z `Account.csv`, więc dwa eksporty mogą mieć **ten sam `do`** (np. `2026-01-08_2026-08-17` i `2026-08-13_2026-08-17`). Nie sumować ich — jeden pakiet na `period_end` (najpóźniejszy `od`), potem jeden wiersz na ISIN. Inaczej MTM / `terminal_unrealized` wychodzi ~2× przy niededuplikowanym CAPEX.
- Do snapshotu / ROI terminal: najnowszy `period_end <= data wyceny`, jeden snapshot jak wyżej.
- **Snapshot:** 1 wiersz — Σ `Wartość w EUR` z `Portfolio.csv` dla gotówki i pozycji. To MTM, nie koszt FIFO.
- **ROI:** per ISIN (`p_degiro:LT0000128621`); BUY → `CAPEX`; SELL → `DIVESTMENT`; `Dywidenda` → `REVENUES`; `is_sold` ⇔ qty≈0 / brak pozycji w najnowszym `Portfolio.csv`.
- `portfolio` / `transactions` / `account` z jednego katalogu muszą się przebudowywać razem. Nowy `Portfolio.csv` + stary `Transactions.csv` daje **Wycena ~2× Inwestycja** (dokupienie w MTM, brak w CAPEX).
- Terminal otwartych = `Wartość w EUR` z `Portfolio.csv` per ISIN; dla zamkniętych terminal = 0.
- Do ROI transakcji używać `Wartość EUR`, a nie `Razem EUR`; opłaty, podatki, FX, cash sweep, depozyty/wypłaty i odsetki są poza XIRR per instrument w v1.
- Implementacja: dedykowany importer DEGIRO, nie parser Revolut; źródła przez DATA_STEP (`01 source`), bez osobnego cache; testy obok istniejących testów brokerów.

### XTB

- W katalogu: `id=p_xtb`, `RODZAJ*=BROKER`, `typ=investment.udziały`, `waluta=PLN` (rachunek `55260027`); bez `roi_def` / `roi_rules`.
- Źródła: eksporty z platformy XTB (ZIP z xStation), nie API. Realny pakiet to jeden XLSX z arkuszami `Open Positions`, `Closed Positions`, `Cash Operations`. Historia zleceń nie występuje w tym eksporcie — poza v1 do czasu osobnej próbki.
- Surowe eksporty XTB przychodzą jako ZIP-y z `~/Downloads`: `{nr_klienta}_{od}_{do}.zip`, dla klienta `55260027`; warianty Windows ` (1)`, ` (2)` traktować jako duplikaty pobrań. ZIP rozpakować, rozpoznać zawartość XLSX/CSV po strukturze arkuszy i zapisać plik kanoniczny w `assets/p_xtb/` jako `xtb_{open,closed,cash}_55260027_{od}_{do}.xlsx` (często `xtb_open_closed_cash_…` gdy ZIP ma wszystkie trzy arkusze); identyczne SHA256 rozpakowanego pliku usuwać jako pominięte, różna treść dla tej samej nazwy docelowej = twardy konflikt.
- Import musi uwzględniać: zakupy, sprzedaże, wpłaty, wypłaty, dywidendy, prowizje, opłaty, podatki, przewalutowania i gotówkę roboczą brokera.
- Parser: nagłówki tabel XTB są przesunięte (Open Positions ok. wiersz 8, Closed/Cash ok. wiersz 4). Kolumny kanoniczne po imporcie: Open (`Product`, `Instrument/Position`, `Ticker`, `Volume`, `Value`, …); Cash (`Type`, `Instrument`, `Ticker`, `Time`, `Amount`, …); Closed (`Instrument`, `Ticker`, `Volume`, `Position ID`, …). Brakujące kolumny uzupełniane puste. Wiersz stopki Cash (`Type=Total` / `Suma`) odrzucać przy imporcie — to nie jest operacja. Open Positions ma wiersz agregatu instrumentu (`Type` puste, `Instrument/Position` = nazwa) oraz wiersze lotów (`Type=BUY/SELL`, `Instrument/Position` = Position ID). Do MTM/ROI brać loty; agregat tylko gdy brak lotów — inaczej Value jest podwójne.
- DATA_STEP (`01 source`): `p_xtb-open.parquet`, `p_xtb-closed.parquet`, `p_xtb-cash.parquet`. **Nie** używać nazw Revolut `p_xtb-trading` / `p_xtb-pnl`. Open to snapshoty (do wyceny brać najnowszy `period_end <= data wyceny`); Cash/Closed to ledger — merge wszystkich plików, dedupe, luka okresów Cash → warning (jak DEGIRO Transactions/Account).
- Normalizacja instrumentów: klucz ROI = ISIN jeśli jest w eksporcie, inaczej ticker XTB (np. `ETFPZUW20M40.PL`). Mapowanie na instrumenty GMS — osobna decyzja; eksport XTB nie dostarcza historycznych market data.
- **Snapshot:** 1 wiersz — Σ `Value` z najnowszego Open Positions ≤ data wyceny: pozycje (wiersze z tickerem) **+ gotówka** z sekcji podsumowania (`Cash` / `Free funds`). To MTM, nie koszt FIFO. Brak katalogu/raportu → brak wiersza (jak DEGIRO).
- **ROI:** per instrument (`p_xtb:TICKER`); merge Cash Operations ze wszystkich eksportów. BUY/`Stock purchase` → `CAPEX`; SELL/`Stock sale` → `DIVESTMENT`; dywidendy → `REVENUES`; `is_sold` ⇔ qty≈0 / brak w najnowszym Open. Wpłaty, wypłaty, prowizje, opłaty, podatki, FX, odsetki **poza XIRR per instrument w v1** (jak DEGIRO). Stopka `Total` poza warningiem. Nieznany prawdziwy `Type` → warning, nie cichy skip.
- GMS: XTB jest źródłem current portfolio/cash do porównania z target portfolio; system generuje rekomendowane transakcje/rebalancing, ale nie wykonuje zleceń automatycznie. Wspólny model: `importers/xtb/normalize.py` → `BrokerPositionFrame` / `BrokerTransactionFrame` / `BrokerCashFlowFrame` / `BrokerCashBalanceFrame`.
- Implementacja: dedykowany importer XTB przez DATA_STEP (`01 source`), walidacja kolumn/typów operacji/duplikatów oraz testy obok istniejących testów brokerów.

### Zadania XTB / GMS / ROI

Zrobione w v1: (1) próbka XLSX i kolumny Open/Closed/Cash; (2) import ZIP → `assets/p_xtb/`; (3) parser + normalizator do wspólnego modelu brokerów; (4) snapshot MTM pozycji + gotówka; (8) warning nieznanego `Type`, dedupe, luka okresów; (9) testy: zakup, sprzedaż, dywidenda, prowizja poza XIRR, wpłata, merge wielu plików.

Pozostaje:
5. Reconciliation XTB ↔ GMS: current portfolio + cash vs target, lista BUY/SELL/rebalance do ręcznego wykonania w XTB.
6. Czysty TWR portfela 2 G-MOMENTUM (strip CF) vs XIRR/MWR — v1 pokazuje ścieżkę NAV ze snapshotów (z dopłatami), nie sumę XIRR tickerów.
7. Metryki: Sharpe, turnover; YTD/DD portfela 2 G-MOMENTUM poza ścieżką NAV v1.
9. (dalsze) częściowa sprzedaż, przewalutowanie i pełny flow XTB → GMS → raport TWR/XIRR, gdy będzie historia zleceń / ISIN w eksporcie.

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
- Zakładka **ROI**: jedno miejsce z pills (Katalog / Revolut robo / depozyty Revolut / depozyty mBank / obligacje / DEGIRO / XTB) — soczewka operacji na koncie; bez zmiany semantyki XIRR. Tabele przepływów per ticker/aktywo: od najnowszej do najstarszej.
- Zakładka **Global momentum**: ranking operacyjny U7 (sygnał na koniec minionego miesiąca) + **as_today** (nieoficjalny nowcast na ostatnim wspólnym close ETF, nie sygnał rebalance; przy nazwie dryf TOP3 vs U7: `*` zostaje, `+` weszło, `-` wypadło) + **Mój GM** (wykonanie) + backtest/benchmarki z sandboxu; ceny Yahoo przez DATA_STEP. **Poland** = `ETFPZUW20M40` (50% WIG20TR + 50% mWIG40TR); bez sWIG80 / pełnego WIG — brak lepszego jednego ETF-a wykonania, zostaje ten ticker.
- Zakładka **Wartość aktywów**: RAP 1 | RAP 2, potem Cash pool (jedna tabela), potem **Inwestycje** jako trzy tabele — `0 OGÓLNY`, `1 REVOLUT-ROBO`, `2 G-MOMENTUM`.
- **Portfel** — każde `investment.*` i `cash_pool.*` należy do dokładnie jednego: **`0 OGÓLNY`** (reszta, w tym cash pool; default nowego aktywa), **`1 REVOLUT-ROBO`** (`p_re_robo`), **`2 G-MOMENTUM`** (`p_degiro` + `p_xtb` + `zloto-monety`; złoto = overlay poza U7). Przypisanie w kodzie (v1); nie kolumna Excela. RAP 1 = portfel × `grupa`; RAP 2 = portfel × `typ` (+ `RAZEM-PLN` = `wartość-pln_eur` + `wartość-pln_pln`). Widok **Mój GM** = portfel `2 G-MOMENTUM`. Snapshot brokerów zostaje 1 wierszem (pozycje + gotówka). Ścieżka NAV ze snapshotów (PLN) vs backtest U7 (serie = 100 na wspólnym starcie) **nie** jest sumą XIRR tickerów i zawiera dopłaty; czysty TWR po CF oraz XIRR całego portfela G-MOMENTUM — później.
- **DATA_STEP** — jedyna warstwa cache i łańcucha zależności. Korzystamy **tylko z API wysokopoziomowego** — w praktyce wyłącznie z metod klasy `DataStep` (np. `init_steps`, `obtain`, `obtain_dependent`, `force_read_data`). Nie wywoływać prywatnych pól/metod (`_dependencies_stack`, `_dependencies`, …) i nie omijać DATA_STEP własnym cache. `roi/cache.py` to produkt domenowy (`10 roi_events`) na DATA_STEP, nie osobny system cache.
- **Yahoo Close** — serie dzienne w `data_steps/yahoo/{ticker}/{as_of}.parquet` przez DATA_STEP (`yahoo_finance.download_yahoo`). Nie do snapshotu / ROI brokerów (MTM online nadal non-goal).
- Komunikacja z użytkownikiem: zwięźle, po polsku jeśli pyta po polsku.

---

## Non-goals (świadomie poza zakresem)

- Pełna speka algorytmów w tym pliku (to jest kod).
- Migracja wszystkich historycznych snapshotów przy każdej zmianie modelu.
- Osobny ledger gotówki bieżącej równoległy do cash pools.
- Osobna wycena całego holdingu złota (dawne `zloto-monety-wyceny`).
- Auto-migracja starego Excela inventory → nowy schemat bez prośby.
- FX w XIRR cash (osobna decyzja, jeśli kiedyś wspólny mianownik PLN z nieruchomościami).
- MTM online instrumentów brokerskich (yfinance/OpenFIGI itd.) — spike OK; produkcja odłożona; snapshot brokerów udziałowych = pozycje (FIFO lub MTM wg źródła) **+ gotówka robocza**; ROI ticker Revolut = last price × qty.
- Klasyczne ROI katalogowe `p_re_robo` / `obligacjeskarbowe` z cash pool / `roi_def` (równolegle do ROI per instrument).
- Fee / TOP-UP / podatki / przelewy PKO w XIRR per instrument; rozbicie instrumentów w tabeli Wartość aktywów → Inwestycje.

---

## Jak aktualizować ten plik

Dopisz / popraw sekcję, gdy zmienia się:
- założenie domenowe,
- znaczenie pojęcia (`typ` / `grupa` / `pool` / `portfel`),
- reguła biznesowa (np. co oznacza sprzedaż),
- kanoniczna nazwa arkusza / kolumny / typu.

Nie zapisuj tu szczegółów implementacji (sygnatury, refaktory) — tylko decyzje i kontekst.



