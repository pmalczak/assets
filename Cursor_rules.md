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
- **IKE:** `IKE-PM` / `IKE-GM` (inventory: Produkt, Data, Liczba jednostek, wartość, waluta) + `IKE-kurs` (Produkt, Data, kurs). Kontenery w `assets`: `pm_ike` → `RODZAJ*=assets.IKE-PM`, `gm_ike` → `assets.IKE-GM` (`typ=investment.udziały`, PLN). Bez wiersza na Produkt w `assets`. CF portfolio: CAPEX/DIVESTMENT z `wartość` (instrument_id = id konta). **MTM:** per Produkt `NAV = Σ Liczba jednostek × kurs(Produkt, ostatnia data ≤ data snapshota)`; suma po produktach; **`data wyceny`** = data ostatniego użytego kursu z `IKE-kurs`. Bez `roi_def` v1 (CF IKE tylko w `portfolio_cf` / Portfele).
- ROI: `roi_def`, `roi_rules`, `roi_manual` (+ opcjonalnie `rules-non-active`)
- **`instruments`** (wymagany): kanoniczna nazwa w UI (`instrument`) + kody źródeł. Kolumny `degiro` (ISIN), `xtb` (ticker XTB), `gm` (ticker Yahoo rankingu U7). Puste = brak na tym źródle. Duplikat nazwy lub kodu = błąd. Brak wiersza dla ISIN/ticker z wyciągu albo 7 tickerów rankingu U7 = twardy błąd. Polska: jeden wiersz `xtb=ETFPZUW20M40.PL` + `gm=ETFPZUW20M40.WA`. Safe GM (`EXVM.DE` / `ETFBCASH.PL`) opcjonalny. Proxy backtestu `ASSETS_7` bez `gm`. Klucz cashflow: `p_degiro:ISIN` / `p_xtb:TICKER`.

---

## Słownik (nie mylić)

| Pojęcie | Znaczenie |
|--------|-----------|
| **cash pool** | Środki pieniężne na kontach ROR (`typ=cash_pool.ror`); runtime `pool_id` (mbank/revolut × PLN/EUR) |
| **investment.\*** | Aktywa nabyte / wyceniane jako inwestycje (w tym ROI `cash`, nieruchomości, złoto, obligacje…) |
| **`id=cash` / `assets.cash`** | Aktywo ROI (np. gotówka „wyprowadzona” do inwestycji), **nie** ewidencja gotówki bieżącej w portfelu |
| **`grupa`** | Agregacja raportowa (wykres wartości portfela) — nie mylić z **portfelem**; RAP1 nie używa `grupa` |
| **portfel** | Przypisanie aktywa (nie nowe ID, nie `grupa`): `0 CASH-POOL` / `0 PŁYNNY` / `1 REVOLUT-ROBO` / `2 G-MOMENTUM` / `3 DŁUGOTERMINOWY` / `4 NIERUCHOMOSCI`. Dotyczy `investment.*` **i** `cash_pool.*`. **`0 CASH-POOL`** = cały `cash_pool.*`. **`0 PŁYNNY`** = domyślny (każde nowe aktywo poza `investment.property` / wyjątkami poniżej; bez cash pool); wszystkie `investment.property` należą do **`4 NIERUCHOMOSCI`**. **`3 DŁUGOTERMINOWY`** = `gm_ike`, `pm_ike`, `rocky-iv`, `obligacjeskarbowe`, `cash`, `zloto-monety`, oraz wyjątek brokerski `p_degiro:LT0000128621` (INTER RAO LIETUVA AB). Nie mylić z plikiem `a_config.xlsx` („katalog aktywów”). |
| **`typ`** | Klasa instrumentu; steruje m.in. `pool_id` i RAP2 |
| **`RODZAJ*`** | Ścieżka ewaluacji / importu (`mbank.*`, `assets.cash`, `assets.properties-wyceny`…) |
| **CAPEX** | Nakłady inwestycyjne (zakup) |
| **REVENUES** | Przychody (odsetki, dywidendy) — nie zmniejszenie pozycji |
| **OPEX** | Wydatki operacyjne (podatek, opłata) |
| **DIVESTMENT** | Cashflow wyjścia kapitału; **nie** OPEX. Dla `investment.property` = sprzedaż (zamknięcie). Dla brokerów/obligacji/depozytów może być częściowe zmniejszenie pozycji |
| **is_sold** | Brak otwartej ekspozycji: `investment.property` ⇔ jest DIVESTMENT ≤ data wyceny; brokerzy `qty≈0`; cash — data zamknięcia z manual |
| **FX_t** | Kurs NBP z **dnia CF** (przeliczenie `amount` → `amount_pln` w ledgerze) |
| **FX_T** | Kurs NBP z **daty wyceny** (stały dla całej serii XIRR lokalnego / ROI_local) |
| **XIRR lokalny** | Kanoniczna rentowność aktywów portfela: CF × FX_T + terminal NAV PLN — **bez ścieżki ruchu kursu** |
| **XIRR PLN (spot)** | Zwrot całkowity w PLN: CF × FX_t + terminal — **aktywo + FX** |
| **ROI_PLN / ROI_local / ROI_FX** | Kwoty P&L (nie stopy); patrz sekcja *XIRR portfela a FX* |
| **udział FX** | `ROI_FX / ROI_PLN` (podpisany); tylko Portfele — nie RAP 1 |

---

## XIRR portfela a FX (`portfolio_cf`)

Dotyczy **nazwanych portfeli** (zakładka Portfele + RAP 1). Warstwa `roi/` (kod) liczy CF/venue w walucie natywnej; cache DATA_STEP razem z ledgerem w **`11 portfolio_cf/{date}/sN/`** (`_catalog`, `_roi_summary`, `_ledger`, …) — bez osobnej zakładki UI.

Ledger instrumentu: `amount` (native) + `currency` + `amount_pln` (= native × FX_t) + terminal NAV już w PLN (= wycena przy FX_T).

### Formuły (P&L w PLN)

```text
ROI_PLN   = Σ amount_pln + terminal_PLN          # spot (FX_t)
ROI_local = Σ amount × FX_T + terminal_PLN       # stały kurs na datę wyceny
ROI_FX    = ROI_PLN − ROI_local
          = Σ amount × (FX_t − FX_T)             # terminal się skraca
udział_FX = ROI_FX / ROI_PLN                     # None gdy |ROI_PLN| ≈ 0
```

### Stopy XIRR

| Metryka | Seria CF | Co mierzy |
|--------|----------|-----------|
| **XIRR lokalny** (kanoniczny; w UI/RAP: `XIRR`) | `amount × FX_T` + terminal | rentowność aktywów bez ruchu FX |
| **XIRR PLN (spot)** (w UI/RAP: `XIRR PLN`) | `amount_pln` + terminal | majątek w PLN łącznie (aktywo + FX) |

Bez osobnego `XIRR(FX)` — IRR nie dekomponuje się addytywnie; udział FX liczymy na **kwotach** P&L.

### Interpretacja `udział FX` (podpisany)

| Wartość | Sens |
|--------|------|
| **0%** | Portfel czysto PLN albo brak różnicy FX_t vs FX_T |
| **0–100%** | FX i aktywa w tę samą stronę co `ROI_PLN` |
| **> 100%** | Strata lokalna (`ROI_local < 0`) skompensowana wzrostem kursu; `ROI_PLN` nadal dodatni |
| **< 0%** | FX zjadł część zysku z aktywów (`ROI_FX < 0` przy dodatnim `ROI_PLN`) |
| **—** | `|ROI_PLN| ≈ 0` albo portfel poza XIRR (`0 CASH-POOL`) |

### Gdzie w UI

- **RAP 1:** `XIRR` (lokalny) + `XIRR PLN` (spot). Bez kolumny udział FX.
- **Portfele (nagłówek):** XIRR lokalny, XIRR PLN, ROI lokalny / ROI FX / ROI PLN, udział FX.
- **Portfele (tabela CF):** wiersze = per instrument (terminal MTM venue); **Razem** = ten sam wynik co nagłówek (`build_portfolio_razem_row` ← `compute_named_portfolio_xirr`). Nie uśredniać XIRR wierszy; nie brać Σ terminali instrumentów jako terminala Razem. XIRR **portfela**: CF bez `*:CASH`; **terminal = NAV pozycji** (NAV snapshota minus gotówka robocza brokerów). Gotówka brokera = skład/NAV majątku, nie ekspozycja XIRR. Kolumny **`quantity`** / **`unit_price`**: z wyciągu przy CAPEX/DIVESTMENT gdy źródło ma cenę (Robo `Price per share`, DEGIRO `Kurs`); XTB Cash Operations — puste. Nie wpływają na XIRR.
- **`Z RAZEM`:** concat CF portfeli poza `0 CASH-POOL` + Σ terminali pozycji (bez gotówki brokerskiej).

### Dual-run vs warstwa `roi/`

Warstwa `roi/` (venue CF, cache w `11 portfolio_cf/…/sN/`) = waluta natywna, bez FX attribution w samym ROI. Agregacja `portfolio_cf` = dual-run w PLN (lokalny + spot) w Portfelach / RAP 1. Dawny produkt `10 roi/` jest przestarzały — usuwa `prune_stale_data_steps`.

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
   - `unit-price-evaluation` (ex `zloto-monety-ceny`) — historia cen kupna per `instrument`; nie wchodzi do MTM
   - `asset-evaluation` (ex `properties-wyceny`) — NAV pozycji (nieruchomości, cash, rocky-iv, …)
   - **Usunięte:** `zloto-monety-wyceny` (wycena całego holdingu złota) — nie wraca; złoto MTM = sztuki × gramy × NBP × 0,99
7. **Złoto ROI** (`asset_id=zloto-monety`):
   - **CAPEX** wyłącznie z `a_config` (`roi_rules` / `roi_manual`) via `allocate_catalog` — jak inne aktywa
   - **Inventory** z arkusza `inventory`; join CAPEX ↔ inventory **wyłącznie po dacie**
   - **Terminal / snapshot:** `data wyceny` = data ostatniej publikacji NBP `cenyzlota` ≤ data snapshota / data obliczenia ROI (weekend i święto biorą poprzedni dzień z serii). `wartość` = sztuki × 31,1034768 g × cena NBP (PLN/g) × 0,99. To szacunek wartości bieżącej (kurs minus 1%), nie kwotowanie dilera. Waga w `inventory` tylko `1oz`; inna waga = twardy błąd. Arkusz `unit-price-evaluation` zostaje historią cen kupna.
   - **Brak / niejednoznaczne / niekompletne inventory** na datę CAPEX → **twardy błąd** (nie warning); CAPEX bez sztuk nie jest pomijany po cichu
8. **ROI cash a FX** — XIRR / ROI nominalny dla `cash` (i innych `RODZAJ*=assets.cash`, np. `rocky-iv`) liczony w **walucie wyceny (EUR)**; bez przeliczania CAPEX/terminal FX w ROI. Przeliczenie na PLN jest w snapshocie portfela (`09 assets`), nie w warstwie ROI cash. W **`portfolio_cf`** (Portfele / RAP 1) CF tych ID mają native + `amount_pln` (NBP z dnia CF); XIRR kanoniczny = constant FX_T; waluta z `assets.waluta` (fallback: `cash`/`rocky-iv` → EUR).
9. **Snapshoty** — raporty UI z `09 assets/*.parquet`; data snapshota = **nazwa pliku** `YYYY-MM-DD.parquet` (bez kolumny `data_wyceny_portfela`). Po zmianie logiki wyceny użytkownik regeneruje snapshot (przycisk w Raportach). Nie migrujemy historycznych parquetów bez prośby. Nowe snapshoty dla gotówki mają `id=cash` (nie `id=EUR`).
   - **`cash_pool.ror` (daty w snapshocie):** `data-ostatniej-transakcji` (wiersz salda), `data-wyciągu` (data **pobrania** pliku / `mtime`; po merge **max** dat pobrań), `data-waluty` (kurs NBP), `liczba dni od wyceny` = `data-waluty − data-wyciągu`. Nie używać ostatniej transakcji jako daty wyciągu. W UI składu (Portfele): `data wyceny` → `data-waluty` → `liczba dni od wyceny` (bez `data-wyciągu` / `data-ostatniej-transakcji`).
10. **Layout Dropbox `INWESTYCJE/`**:
    - `assets/` — `a_config.xlsx` (ex `assets_1` + `analyse_assets_config`), katalogi aktywów `investment.*`
    - `cash_pool/` — katalogi aktywów `cash_pool.*` (wyciągi ROR mBank/Revolut)
    - `download/pm|gm/` — źródło importu Revolut
    - Import wyciągów ROR trafia do `cash_pool/`; wyjątki w `assets/`: trading Revolut (`p_re_robo`), obligacje skarbowe (`obligacjeskarbowe`)
    - Wyciąg, którego okres z nazwy **całkowicie zawiera się** w innym pliku tego samego rodzaju (to samo konto mBank / ten sam prefix Revolut `account-statement` lub `savings-statement`) jest zbędny — `maintenance/prune_contained_statements.py` (domyślnie dry-run; `--delete` kasuje). Równe okresy: zostaje jeden plik. UUID depozytów (bez dat w nazwie) poza tą regułą. Ten sam skrypt raportuje **luki** między pozostałymi okresami (next.start > prev.end + 1 dzień), np. `…_200101_200228` i `…_200315_200630`.
11. **Portfel** — każde `investment.*` i `cash_pool.*` ma dokładnie jeden: `0 CASH-POOL` (cały `cash_pool.*`), `0 PŁYNNY` (default inwestycji poza wyjątkami), `1 REVOLUT-ROBO`, `2 G-MOMENTUM`, `3 DŁUGOTERMINOWY` (`gm_ike` / `pm_ike` / `rocky-iv` / `obligacjeskarbowe` / `cash` / `zloto-monety` / `p_degiro:LT0000128621` INTER RAO) albo `4 NIERUCHOMOSCI` (każde `investment.property`). Nie jest to `grupa` ani osobny wiersz katalogu. RAP 1 = portfel → `RAZEM` + `udział` % + **`XIRR`** + **`XIRR PLN`** (semantyka: sekcja *XIRR portfela a FX*; `0 CASH-POOL` → `—`). RAP 2 = portfel × typ (+ `RAZEM-PLN`).
12. **Kolejność i format kolumn w UI** — `wartość` → `waluta` → `wartość-pln`, potem `data wyceny` → `data-waluty` → `liczba dni od wyceny`. `wartość` i `wartość-pln` jak kwoty: spacje tysięcy, bez części dziesiętnej, wyrównane do prawej (`column_config` z `alignment="right"`, bo kwoty idą do UI jako tekst). Dotyczy tabel składu w zakładce Portfele i ewaluacji w Waliduj.

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

mBank: pliki `*_ *_ *.csv` (stem 22 znaki) z `~/Downloads` oraz luźne CSV w `assets/` → katalogi kont w `cash_pool/` po kluczu = ostatnie 4 znaki pierwszego segmentu nazwy (= 4. segment katalogu, np. `p_m_23_2330` ↔ `…2330_…`). Brak katalogu = twardy błąd z listą znanych rachunków (nie `KeyError`).

**Data wyciągu (wszystkie importy):** `ref_date` / `FILE_DATE` = **data pobrania pliku** (`mtime` źródła; w nazwie kanonicznej trzecia data, gdy okres `{od}_{do}` jest rekonstruowany z transakcji). **Nigdy** data ostatniej transakcji ani sam `period_end` ledgeru. Okres `{od}_{do}` zostaje osobno (nazwa banku albo min/max txn) i **tylko on** idzie do kontroli luk (`period_coverage`) — nie `FILE_DATE`. DEGIRO / Trade Republic / historia PKO: `{kind}_{od}_{do}_{data_wyciągu}`. Katalog ROI (`roi_def`) poza zakresem.

### ROI lokat mBank

- Osobna venue ROI (nie `roi_def`).
- Snapshot **Aktywa**: 1 wiersz `investment.depozyt` na konto mBank (`id` = konto ROR); `VALUE` = Σ kapitał otwartych lokat (−CAPEX). Zamknięte lokaty nie wchodzą. Szczegóły CF per NR — w Portfelach (ledger `portfolio_cf`).
- Klucz ROI: `{account_id}:{NR 15 cyfr}` z `#Tytuł` (`\bNR \d{15}\b`). `#Opis operacji` mapuje CF.
- `OTW. LOKATY NR …` (przelew wychodzący) → `CAPEX`; `ZERWANIE` / `WYGAŚNIĘCIE` → `DIVESTMENT` (sam kapitał, **pełne zamknięcie**); `ODSETKI LOKAT TERMINOWYCH` → `REVENUES`; `PODATEK OD ODSETEK…` **z NR** → `OPEX`. Podatek ROR bez NR i przelewy bez `OTW. LOKATY` poza ROI.
- Terminal otwartej = −Σ CAPEX (kapitał; odsetki już na ROR). Po DIVESTMENT: `is_sold`, terminal 0. `roi_nominal` = odsetki netto (REVENUES+OPEX).

Trade Republic (PM): `Eksport transakcji.csv` z `download/pm` → `assets/p_traderepublic/eksport-transakcji_{od}_{do}_{data_wyciągu}.csv` (`od`/`do` = min/max kolumny `date`; trzecia data = pobranie). Merge wielu plików: **luka okresów → twardy błąd**; overlap → dedupe po `transaction_id`. W katalogu: `id=p_traderepublic`, `RODZAJ*=BROKER`, `typ=investment.udziały`, `waluta=PLN`; bez `roi_def`. Snapshot na start: 1 wiersz NAV=0 (mapowanie BUY/SELL / ROI per instrument — osobna decyzja).

Obligacje skarbowe (PKO BP): `StanRachunkuRejestrowego*.xls` oraz `HistoriaDyspozycji.xls` z `~/Downloads` → `assets/obligacjeskarbowe`. Przy przenoszeniu historia dostaje nazwę `{YYYY-MM-DD} {YYYY-MM-DD} {data_wyciągu} HistoriaDyspozycji.xls` (min/max `DATA DYSPOZYCJI` + data pobrania). Jeśli w katalogu jest już plik zawierający wszystkie transakcje z nowego — nowy jest usuwany (pominięty); nadpisanie tej samej nazwy/zawartości nie jest błędem. Stan: `FILE_DATE` = data z nazwy pliku PKO (as-of MTM, nie last txn).

---

## Rachunek brokerski (Revolut robo + obligacje skarbowe PKO + Trade Republic + DEGIRO + XTB)

- To **nie** jest `cash_pool` ani pojedyncza inwestycja-lump z przelewu ROR — kontener pozycji instrumentów (+ gotówka robocza brokera).
- **Gotówka robocza / konto depozytowe brokera** (DEGIRO, XTB, Revolut robo, przyszłe obligacje skarbowe / inne `RODZAJ*=BROKER`):
  - **skład + NAV majątku** — tak (saldo na rachunku);
  - **CF ledger / tabela XIRR / picker / Excel CF** — nie (`*:CASH` nie powstaje);
  - **XIRR portfela / instrumentów** — dotyczy pozycji (papiery), nie wolnej gotówki; terminal XIRR portfela = NAV pozycji (bez cash).
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
- **Snapshot:** 1 wiersz — Σ **ostatni kurs z blottera × qty** otwartych pozycji (MTM bez kursu bieżącego; qty z FIFO) **+ gotówka robocza z blottera** (TOP-UP / SELL / DIVIDEND − BUY / FEE). Brak ceny transakcji → fallback koszt FIFO lotu. Sama gotówka (wpłata bez kupna) też daje wiersz. `data wyceny` = `min(data snapshota, data-wyciągu)` — świeżość pobrania blottera, nie data ostatniej transakcji (brak transakcji nie oznacza starego wyciągu). XIRR portfela `1 REVOLUT-ROBO`: terminal = NAV **pozycji** (bez gotówki); gotówka tylko w składzie.
- **ROI:** per ticker (`p_re_robo:PRAR`); BUY → `CAPEX`; SELL → `DIVESTMENT`; DIVIDEND → `REVENUES`; `ROBO MANAGEMENT FEE` → `OPEX` na sztucznym tickera `REVOLUT-ROBO` (`p_re_robo:REVOLUT-ROBO`; bez XIRR wiersza, `is_sold=false` — OPEX wchodzi do Razem); TOP-UP poza XIRR; `is_sold` ⇔ qty≈0 (poza `REVOLUT-ROBO`).
- Terminal otwartych (ROI i snapshot pozycji) = last trade price × qty; `is_sold` ⇔ qty == 0.
- Reconciliacja: Σ `CASH TOP-UP` vs `|To Robo portfolio|` na `revolut_eur` (tol. 0.01 EUR).

### DEGIRO

- W katalogu: `id=p_degiro`, `RODZAJ*=BROKER`, `typ=investment.udziały`, `waluta=EUR`; bez `roi_def` / `roi_rules`.
- Źródła: pakiet `Portfolio.csv`, `Transactions.csv`, `Account.csv` z `~/Downloads`; import pakietowy do `assets/p_degiro/`.
- Import wymaga kompletu 3 plików. Okres pakietu = `min(Data)..max(Data)` z pierwszej kolumny `Data` w `Account.csv` (data księgowania); te same daty obowiązują wszystkie trzy pliki.
- Nazwy docelowe: `portfolio_{od}_{do}_{data_wyciągu}.csv` (oraz transactions/account). `{od}_{do}` z min/max `Data` w Account.csv (**okno aktywności** księgowań, nie zadeklarowany zakres eksportu); **data wyciągu** = data pobrania pakietu, nie ostatnia txn. `FILE_DATE` / trzecia data służą świeżości — **nie** kontroli luk okresów.
- Format eksportu PL: separator CSV `,`, liczby z przecinkiem dziesiętnym w cudzysłowie; w `Account.csv` są dwie kolumny `Data` i puste nagłówki walut — importer nadaje nazwy techniczne (`booking_date`, `value_date`, `change_currency`, `balance_currency`).
- Przy przenoszeniu: istniejący identyczny/obejmujący pakiet (Account/Transactions) → skip + usunięcie incoming; **ten sam `{od}_{do}` z innym Portfolio** (świeższy MTM / nowe pozycje, ledger bez nowych wierszy) → podmiana samego `portfolio_*.csv` (nowa `data_wyciągu`); incoming z **nadzbiorem** księgowań → podmiana całego pakietu; rozjechane historie ledgeru → twardy konflikt.
- Przy odczycie wielu pakietów: `Transactions` dedupe po `Identyfikator zlecenia` + polach transakcji; `Account` dedupe po pełnym kluczu księgowania. Overlap / zawarte okresy OK — luka = po **scaleniu** nazwanych `{od}_{do}` (`period_coverage`; `next.start ≤ prev.end + 1`). Soft warning w v1; ciche dni między oknami aktywności mogą nadal warnować. Zbędne pliki zawarte w dłuższym eksporcie tego samego prefixu: `maintenance/prune_contained_degiro.py` (dry-run; `--delete`).
- `Portfolio.csv` nie jest ledgerem; to snapshot na datę. Okres pakietu pochodzi z `Account.csv`, więc dwa eksporty mogą mieć **ten sam `do`** (np. `2026-01-08_2026-08-17` i `2026-08-13_2026-08-17`). Nie sumować ich — jeden pakiet na `period_end` (najpóźniejszy `od`), potem jeden wiersz na ISIN. Inaczej MTM / `terminal_unrealized` wychodzi ~2× przy niededuplikowanym CAPEX.
- Do snapshotu / ROI terminal: najnowszy `period_end <= data wyceny`, jeden snapshot jak wyżej.
- **Snapshot:** 1 wiersz — Σ `Wartość w EUR` z `Portfolio.csv` dla gotówki i pozycji. To MTM, nie koszt FIFO.
- **ROI:** per ISIN (`p_degiro:LT0000128621`); w UI nazwa z `instruments.instrument` (kolumna `degiro`). BUY → `CAPEX`; SELL → `DIVESTMENT`; `Dywidenda` → `REVENUES`; `is_sold` ⇔ qty≈0 / brak pozycji w najnowszym `Portfolio.csv`.
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
- DATA_STEP (`01 source`): `p_xtb-open.parquet`, `p_xtb-closed.parquet`, `p_xtb-cash.parquet`. **Nie** używać nazw Revolut `p_xtb-trading` / `p_xtb-pnl`. Open to snapshoty (do wyceny brać najnowszy `period_end <= data wyceny`); Cash/Closed to ledger — merge wszystkich plików, dedupe; luka okresów Cash → soft warning po **scaleniu** nazwanych `{od}_{do}` z ZIP (`period_coverage`, jak DEGIRO). `FILE_DATE` (mtime) poza kontrolą luk.
- Normalizacja instrumentów: klucz ROI = ISIN jeśli jest w eksporcie, inaczej ticker XTB (np. `ETFPZUW20M40.PL`). Prezentacja = `instruments.instrument` (kolumna `xtb`). Kolumna `gm` = ticker Yahoo rankingu U7 (osobny listing, np. `.WA` vs `.PL`).
- **Snapshot:** 1 wiersz — Σ `Value` z najnowszego Open Positions ≤ data wyceny: pozycje (wiersze z tickerem) **+ gotówka**. Gotówka: najpierw summary Open (`Cash` / `Free funds`); gdy brak — `Amount` z footera `Type=Total`/`Suma` w Cash Operations (saldo PLN; **nie** CF/ROI). To MTM, nie koszt FIFO. Brak katalogu/raportu → brak wiersza (jak DEGIRO).
- **ROI:** per ticker (`p_xtb:TICKER`); w UI nazwa z `instruments`. Merge Cash Operations ze wszystkich eksportów. BUY/`Stock purchase` → `CAPEX`; SELL/`Stock sale` → `DIVESTMENT`; dywidendy → `REVENUES`; `is_sold` ⇔ qty≈0 / brak w najnowszym Open. Wpłaty, wypłaty, prowizje, opłaty, podatki, FX, odsetki **poza XIRR per instrument w v1** (jak DEGIRO). Stopka `Total` poza warningiem. Nieznany prawdziwy `Type` → warning, nie cichy skip.
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
- **Portfel (v1):** cały kontener `obligacjeskarbowe` (+ emisje `obligacjeskarbowe:*`) → `3 DŁUGOTERMINOWY`. Uzasadnienie: dziś w praktyce jedna seria 10-letnia — traktujemy rachunek jak jeden instrument długoterminowy.
- **Na przyszłość (wiele zapadalności):** mapować **per emisja** (`obligacjeskarbowe:KOD`) do różnych portfeli wg terminu zapadalności. CF/ROI per kod już jest; wtedy domknąć model **BROKER / INSTRUMENT** jak Robo/DEGIRO — NAV/terminal portfela ze **składników emisji** (nie samego blobu kontenera), żeby CF i Razem się nie rozjeżdżały przy rozdziale między portfele.

- Lepsze MTM online (API) — osobna decyzja później.

---

## Preferencje pracy z kodem

- Python przez `uv run` z katalogu `app/`.
- Nie commitować bez prośby; nie pushować bez prośby.
- **`data_steps/` cache — nigdy na GitHub** (m.in. `*.parquet`, `*.xls`, `*.xlsx`, `_metadata.json`, `_metadata.lock`, cały `_ui/`: snapshoty, FX, Yahoo, `01 source`, ROI, przypadkowe wyciągi, lokalne preferencje UI). Nie `git add` / commit / push. Fixtures w `app/unit_testing/data_steps/` wolno. Regeneracja: UI / pipeline, nie klon repo.
- **Git ↔ GitHub:** jedyna gałąź synchronizowana z remote to **`main`**. Inne gałęzie zostają lokalne — bez `push` / `pull` / `-u` / trackingu na GitHub, chyba że użytkownik wyraźnie każe inaczej w bieżącej rozmowie.
- Nie dodawać zbędnych markdownów / refaktorów poza zakresem zastosowania.
- Testy obok zmiany reguły (unittest w `app/unit_testing/`).
- Streamlit: cache `@st.cache_data` — przy zmianie kształtu wyniku podbić `_schema` / `clear()`.
- Globalny filtr pozycji (sidebar): Niesprzedane / Sprzedane / Wszystkie — tabele CF/XIRR w Portfelach wg `is_sold`. Preferencja lokalna w `data_steps/_ui/sold_filter.txt` (nie w git). Snapshoty i tak pomijają `VALUE=0`.
- Zakładka **Waliduj**: walidacja ROI (`roi_def`/`roi_rules`/`roi_manual` / `instruments`) + ewaluacja katalogu `assets` w `a_config.xlsx` (dry-run, bez zapisu snapshotu).
- Zakładka **Maintenance** (po Waliduj): UI do `prune_contained_statements` (cash_pool), `prune_contained_degiro` (p_degiro) oraz `prune_stale_data_steps` (stare `sN` pod `11 portfolio_cf/{date}/` + całe przestarzałe produkty np. `10 roi/`; czyści `_metadata.json`); domyślnie dry-run, opcjonalnie usuwanie jak `--delete`.
- Zakładka **Portfele**: NAV i skład nazwanych portfeli ze snapshotów (`wartość` → `waluta` → `wartość-pln` → daty wyceny). Metryki XIRR/ROI/FX — sekcja **XIRR portfela a FX** (`app/portfolio_cf`, cache `11 portfolio_cf`). `0 CASH-POOL` poza XIRR. CF ledger zawsze widoczny (w tym **Kontrahent** z cash-pool / `AccountTx.counterparty` — do rekonsyliacji z rejestrem transakcji); tabela per instrument + Razem = nagłówek. `2 G-MOMENTUM` i `1 REVOLUT-ROBO`: skład per instrument (+ gotówka robocza); CF/XIRR bez cash. Tylko GM: NAV vs backtest U7. Ścieżka NAV ze snapshotów zawiera dopłaty (to nie TWR). Wynik strategii GM jest tu (`2 G-MOMENTUM`), nie w osobnej zakładce ROI.

- Zakładka **Global momentum**: ranking operacyjny U7 (sygnał na koniec minionego miesiąca) + **as_today** (nieoficjalny nowcast na ostatnim wspólnym close ETF, nie sygnał rebalance; przy nazwie dryf TOP3 vs U7: `*` zostaje, `+` weszło, `-` wypadło) + backtest/benchmarki z `app/global_momentum`; ceny Yahoo przez DATA_STEP. **Poland** = `ETFPZUW20M40` (50% WIG20TR + 50% mWIG40TR); bez sWIG80 / pełnego WIG — brak lepszego jednego ETF-a wykonania, zostaje ten ticker. Kolumna **Asset** w Ranking U7 / as_today = `instruments.instrument` (join po `gm`); **Ticker** zostaje kodem Yahoo. Prefiksy dryfu zostają na Asset. Wewnętrzny ranking nadal po kluczach uniwersum (`USA`, `Japan`, …).
- Zakładka **Aktywa**: u góry kontrolki snapshota obok RAP 1 (bez tytułu); poniżej RAP 2 na pełnej szerokości od lewej. RAP 1: `RAZEM` + `udział` + **`XIRR`** + **`XIRR PLN`** (z `portfolio_cf`; semantyka — *XIRR portfela a FX*). Skład aktywów według portfeli — wyłącznie zakładka **Portfele**.
- **Portfel** — każde `investment.*` i `cash_pool.*` należy do dokładnie jednego: **`0 CASH-POOL`** (cały `cash_pool.*`), **`0 PŁYNNY`** (default nowych inwestycji poza wyjątkami), **`1 REVOLUT-ROBO`** (`p_re_robo` + instrumenty `p_re_robo:*`), **`2 G-MOMENTUM`** (`p_degiro`/`p_xtb` + instrumenty `p_degiro:*`/`p_xtb:*`, **bez** override poniżej), **`3 DŁUGOTERMINOWY`** (`gm_ike`, `pm_ike`, `rocky-iv`, `obligacjeskarbowe` + emisje `obligacjeskarbowe:*`, `cash`, `zloto-monety`, **`p_degiro:LT0000128621`** INTER RAO LIETUVA AB), **`4 NIERUCHOMOSCI`** (wszystkie `investment.property`). Jednostka ledger/XIRR = **instrument**; mapa startowa = stan obecny (całe ROBO→ROBO, DEGIRO/XTB→GM) + wyjątki `INSTRUMENT_PORTFOLIO_OVERRIDES`. NAV snapshota: blob brokera jest w runtime dzielony (`split_broker_nav_for_instrument_overrides`) — wartość override schodzi z konta GM i wchodzi do docelowego portfela. Gotówka robocza brokera: skład/NAV tak, CF/XIRR nie (sekcja rachunek brokerski). Przypisanie w kodzie (v1). RAP 1 z XIRR portfeli; RAP 2 bez zmian. Widok GM / Robo = **Portfele**.
- **DATA_STEP** — jedyna warstwa cache i łańcucha zależności. Korzystamy **tylko z API wysokopoziomowego** — w praktyce wyłącznie z metod klasy `DataStep` (np. `init_steps`, `obtain`, `obtain_dependent`, `force_read_data`). Nie wywoływać prywatnych pól/metod (`_dependencies_stack`, `_dependencies`, …) i nie omijać DATA_STEP własnym cache. **`11 portfolio_cf/{date}/sN/`** (stałe w `app_proc/portfolio_cf_step.py` — poza pakietem `portfolio_cf`, żeby uniknąć cykli importu): `_catalog` / `_roi_summary` (venue ROI z `roi/roi_products.py`) + `_ledger` / `_coverage` / `_warnings` / `_xirr` (`portfolio_cf/products.py`). UI Portfele / RAP 1: `load_assembly` / `load_portfolio_metrics_map`. **Inicjalizacja:** raz na proces w entrypoincie (`init_app_data_step()` z `app_assets.main` / CLI); nie w adapterach ani `download_yahoo`. Osobny proces (`snapshot_cli`) = własny init.
- **Yahoo Close** — serie dzienne w `data_steps/yahoo/{ticker}/{as_of}.parquet` przez DATA_STEP (`yahoo_finance.download_yahoo`). Nie do snapshotu / ROI brokerów (MTM online nadal non-goal).
- **NBP FX** — cache kursów wyłącznie w `data_steps/fx/` (`NBP_FX_RATES.*.parquet`); nie w root `data_steps/`. Ścieżka: `get_nbp_fx_cache_dir()`.
- Komunikacja z użytkownikiem: zwięźle, po polsku jeśli pyta po polsku.

---

## Non-goals (świadomie poza zakresem)

- Pełna speka algorytmów w tym pliku (to jest kod).
- Migracja wszystkich historycznych snapshotów przy każdej zmianie modelu.
- Osobny ledger gotówki bieżącej równoległy do cash pools.
- Osobna wycena całego holdingu złota (dawne `zloto-monety-wyceny`). Snapshot `investment.złoto-monety` to sztuki × NBP × 0,99, nie arkusz NAV.
- Auto-migracja starego Excela inventory → nowy schemat bez prośby.
- Osobny `XIRR(FX)` ani dekompozycja stopy IRR na FX (udział FX tylko z kwot P&L — sekcja *XIRR portfela a FX*).
- MTM online instrumentów brokerskich (yfinance/OpenFIGI itd.) — spike OK; produkcja odłożona; snapshot brokerów udziałowych = pozycje (MTM ze źródła: DEGIRO/XTB eksport; Robo = last trade × qty z blottera) **+ gotówka robocza**. Złoto jest poza tym zakazem: szacunek NBP × 0,99.
- Klasyczne ROI katalogowe `p_re_robo` / `obligacjeskarbowe` z cash pool / `roi_def` (równolegle do ROI per instrument).
- Zakładka UI **ROI** (pills Katalog / brokerzy / depozyty) — usunięta; CF i XIRR w **Portfele** (`portfolio_cf`). Warstwa `roi/` zostaje jako źródło CF dla adapterów.
- Fee / TOP-UP / podatki / przelewy PKO w XIRR **per instrument ETF** (Revolut: FEE jest na `REVOLUT-ROBO` i w Razem; TOP-UP nadal poza); rozbicie instrumentów GM — zakładka Portfele.

---

## Jak aktualizować ten plik

Dopisz / popraw sekcję, gdy zmienia się:
- założenie domenowe,
- znaczenie pojęcia (`typ` / `grupa` / `pool` / `portfel` / XIRR lokalny vs PLN / udział FX),
- reguła biznesowa (np. co oznacza sprzedaż),
- kanoniczna nazwa arkusza / kolumny / typu.

Nie zapisuj tu szczegółów implementacji (sygnatury, refaktory) — tylko decyzje i kontekst.



