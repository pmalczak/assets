#!/usr/bin/env python3
"""
Skrypt do sprawdzania cen skupu/sprzedaży złotych monet bulionowych w Polsce.

Źródła:
  - Tavex (tavex.pl)            — jeden z największych dealerów
  - Mennica Kapitałowa          — skup + sprzedaż, wiele oddziałów
  - NumiTracker (numitracker.com) — porównywarka ~60 dealerów (ranking najtańszych)

Wymagania:
  pip install requests beautifulsoup4 lxml rich

Użycie:
  python gold_coins_pl.py               # wszystkie monety 1 oz złota
  python gold_coins_pl.py --weight 1/4oz
  python gold_coins_pl.py --source tavex
  python gold_coins_pl.py --all         # scrapuj wszystkie wagi i źródła
"""

import argparse
import sys
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
}

TIMEOUT = 15

WEIGHT_ALIASES = {
    "1oz": "1oz",
    "1/2oz": "1/2oz",
    "1/4oz": "1/4oz",
    "1/10oz": "1/10oz",
    "1/20oz": "1/20oz",
    "1/25oz": "1/25oz",
}

# ---------------------------------------------------------------------------
# 1. TAVEX
# ---------------------------------------------------------------------------

def scrape_tavex(weight: str = "1oz") -> list[dict]:
    """
    Zwraca listę monet z cenami ze strony Tavex.
    Tavex renderuje ceny dynamicznie — bierzemy listę produktów
    ze strony kategorii i wyciągamy dane z atrybutów data-*.
    """
    url = "https://tavex.pl/zloto/zlote-monety-bulionowe/"
    results = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # Tavex używa <div class="product-item"> lub podobnych
        # Próbujemy kilka selektorów
        items = soup.select(".product-item, .product-card, article.product")
        if not items:
            # fallback: szukamy bloków z ceną
            items = soup.select("[class*='product']")

        for item in items:
            name_el = item.select_one(
                ".product-title, .product-name, h2, h3, [class*='title']"
            )
            if not name_el:
                continue
            name = name_el.get_text(strip=True)

            # Filtrowanie po wadze
            if weight.lower() not in name.lower() and weight.replace("oz", " oz") not in name.lower():
                continue

            def get_price(sel_list):
                for sel in sel_list:
                    el = item.select_one(sel)
                    if el:
                        txt = el.get_text(strip=True).replace("\xa0", " ")
                        return txt
                return "—"

            buy_price = get_price([
                "[class*='buy'], [class*='skup'], [class*='buyback']",
                "[data-price-buy]",
            ])
            sell_price = get_price([
                "[class*='sell'], [class*='sprzedaz'], [class*='price']:not([class*='buy'])",
                "[data-price-sell]",
                ".price",
            ])

            results.append({
                "source": "Tavex",
                "name": name[:60],
                "buy": buy_price,
                "sell": sell_price,
                "url": url,
            })

    except requests.RequestException as e:
        console.print(f"[red]Tavex błąd połączenia:[/red] {e}")
    except Exception as e:
        console.print(f"[red]Tavex błąd parsowania:[/red] {e}")

    return results


# ---------------------------------------------------------------------------
# 2. MENNICA KAPITAŁOWA — strona skupu
# ---------------------------------------------------------------------------

def scrape_mennica_kapitalowa() -> list[dict]:
    """
    Strona skupu Mennicy Kapitałowej zawiera tabelę HTML z cenami.
    """
    url = "https://mennicakapitalowa.pl/Skup-metali-szlachetnych-cena-odkupu-monet-sztabek-i-zlomu-ccms-pol-32.html"
    results = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            headers_row = rows[0] if rows else None
            if not headers_row:
                continue
            col_texts = [th.get_text(strip=True).lower() for th in headers_row.find_all(["th", "td"])]
            # Szukamy tabeli z kolumnami ceny
            if not any(k in " ".join(col_texts) for k in ["nazwa", "cena", "skup", "moneta"]):
                continue

            for row in rows[1:]:
                cols = row.find_all(["td", "th"])
                if len(cols) < 2:
                    continue
                name = cols[0].get_text(strip=True)
                if not name or len(name) < 3:
                    continue
                # Zazwyczaj: col 0 = nazwa, col 1 = skup, col 2 = sprzedaż (lub tylko skup)
                buy = cols[1].get_text(strip=True) if len(cols) > 1 else "—"
                sell = cols[2].get_text(strip=True) if len(cols) > 2 else "—"

                results.append({
                    "source": "Mennica Kapitałowa",
                    "name": name[:60],
                    "buy": buy,
                    "sell": sell,
                    "url": url,
                })

    except requests.RequestException as e:
        console.print(f"[red]Mennica Kapitałowa błąd połączenia:[/red] {e}")
    except Exception as e:
        console.print(f"[red]Mennica Kapitałowa błąd parsowania:[/red] {e}")

    return results


# ---------------------------------------------------------------------------
# 3. NUMITRACKER — porównywarka cen
# ---------------------------------------------------------------------------

def scrape_numitracker(weight: str = "1oz", transaction: str = "sprzedaz") -> list[dict]:
    """
    NumiTracker agreguje oferty ~60 dealerów.
    Pobiera ranking najtańszych monet danej wagi.

    transaction: 'sprzedaz' (kupujesz) lub 'skup' (sprzedajesz)
    """
    # Mapowanie weight → parametr URL
    url = f"https://numitracker.com/produkty/zloto?metal_form_type=moneta&weight={weight}"
    results = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # NumiTracker renderuje listę produktów po stronie klienta (Next.js),
        # dlatego dane mogą być w tagu <script id="__NEXT_DATA__">
        import json
        script = soup.find("script", id="__NEXT_DATA__")
        if script:
            data = json.loads(script.string)
            # Ścieżka do produktów może się zmieniać, przeglądamy rekurencyjnie
            products = _find_key(data, "products") or _find_key(data, "items") or []
            for p in products[:20]:  # max 20 wyników
                name = p.get("name") or p.get("title") or p.get("fullName") or "?"
                offers = p.get("offers") or p.get("prices") or []
                if offers:
                    # Szukamy najtańszej oferty sprzedaży / skupu
                    buy_prices = [
                        o.get("buyPrice") or o.get("buy_price") or o.get("price")
                        for o in offers if o.get("type") in ("buy", "buyback", "skup", None)
                    ]
                    sell_prices = [
                        o.get("sellPrice") or o.get("sell_price") or o.get("price")
                        for o in offers if o.get("type") in ("sell", "sprzedaz", None)
                    ]
                    buy_prices = [x for x in buy_prices if x]
                    sell_prices = [x for x in sell_prices if x]
                    buy_str = f"{min(buy_prices):.2f} zł" if buy_prices else "—"
                    sell_str = f"{min(sell_prices):.2f} zł" if sell_prices else "—"
                else:
                    buy_str = str(p.get("minBuyPrice") or p.get("buy") or "—")
                    sell_str = str(p.get("minSellPrice") or p.get("sell") or "—")
                    if buy_str != "—":
                        buy_str += " zł"
                    if sell_str != "—":
                        sell_str += " zł"

                results.append({
                    "source": "NumiTracker",
                    "name": str(name)[:60],
                    "buy": buy_str,
                    "sell": sell_str,
                    "url": url,
                })
        else:
            # Brak danych SSR — informujemy użytkownika
            console.print(
                "[yellow]NumiTracker:[/yellow] Strona renderowana po stronie klienta (JavaScript). "
                "Użyj przeglądarki lub narzędzia takiego jak Playwright/Selenium, aby uzyskać pełne dane.\n"
                f"Otwórz ręcznie: [link={url}]{url}[/link]"
            )

    except requests.RequestException as e:
        console.print(f"[red]NumiTracker błąd połączenia:[/red] {e}")
    except Exception as e:
        console.print(f"[red]NumiTracker błąd parsowania:[/red] {e}")

    return results


def _find_key(obj, key):
    """Rekurencyjne wyszukiwanie klucza w zagnieżdżonej strukturze JSON."""
    if isinstance(obj, dict):
        if key in obj:
            val = obj[key]
            if isinstance(val, (list, dict)) and val:
                return val
        for v in obj.values():
            result = _find_key(v, key)
            if result:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = _find_key(item, key)
            if result:
                return result
    return None


# ---------------------------------------------------------------------------
# 4. KURS ZŁOTA (NBP / open-source)
# ---------------------------------------------------------------------------

def get_gold_spot_pln() -> str:
    """Pobiera kurs złota z API NBP (publiczne, bez klucza)."""
    try:
        # NBP udostępnia kurs USD/PLN
        nbp = requests.get(
            "https://api.nbp.pl/api/exchangerates/rates/A/USD/?format=json",
            timeout=TIMEOUT,
        ).json()
        usd_pln = nbp["rates"][0]["mid"]

        # Spot złota w USD/oz (używamy bezpłatnego endpointu)
        metal = requests.get(
            "https://api.metals.live/v1/spot/gold",
            timeout=TIMEOUT,
        ).json()
        gold_usd = metal[0].get("gold") if isinstance(metal, list) else metal.get("gold")

        if gold_usd and usd_pln:
            gold_pln = float(gold_usd) * float(usd_pln)
            return f"{gold_pln:,.2f} zł/oz  ({gold_usd} USD × {usd_pln} PLN)"
    except Exception:
        pass

    # Fallback: tylko z Metals-API (zwraca PLN bezpośrednio, jeśli dostępny)
    try:
        r = requests.get("https://api.metals.live/v1/spot", timeout=TIMEOUT).json()
        gold_usd = None
        for item in (r if isinstance(r, list) else [r]):
            gold_usd = item.get("gold") or gold_usd
        if gold_usd:
            return f"{gold_usd} USD/oz (przeliczenie PLN niedostępne)"
    except Exception:
        pass

    return "niedostępny"


# ---------------------------------------------------------------------------
# 5. WYŚWIETLANIE
# ---------------------------------------------------------------------------

def display_results(all_results: list[dict], weight: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    spot = get_gold_spot_pln()

    console.print()
    console.rule(f"[bold yellow]🪙 Złote monety bulionowe — {weight}[/bold yellow]")
    console.print(f"  [dim]Pobrano:[/dim] {now}   |   [dim]Kurs spot złota:[/dim] {spot}")
    console.print()

    if not all_results:
        console.print("[red]Brak danych do wyświetlenia.[/red]")
        return

    table = Table(
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
        expand=True,
        width=600,     # <-- dodaj to: ustaw konkretną szerokość w znakach

    )
    table.add_column("Źródło", style="bold", min_width=20)
    table.add_column("Moneta / produkt", min_width=30)
    table.add_column("Skup (ty sprzedajesz)", justify="right", style="green")
    table.add_column("Sprzedaż (ty kupujesz)", justify="right", style="yellow")
    table.add_column("URL", style="dim blue")

    for r in all_results:
        table.add_row(
            r["source"],
            r["name"],
            r["buy"],
            r["sell"],
            r["url"],
        )

    console.print(table)
    console.print()
    console.print(
        "[dim]Uwaga: ceny mogą być nieaktualne lub niedostępne, jeśli strona używa dynamicznego JS.\n"
        "W takim przypadku otwórz podany URL bezpośrednio w przeglądarce.[/dim]"
    )
    console.print()


# ---------------------------------------------------------------------------
# 6. MAIN
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Sprawdź ceny skupu/sprzedaży złotych monet bulionowych w Polsce."
    )
    parser.add_argument(
        "--weight",
        default="1oz",
        choices=list(WEIGHT_ALIASES.keys()),
        help="Waga monety (domyślnie: 1oz)",
    )
    parser.add_argument(
        "--source",
        default="all",
        choices=["all", "tavex", "mennica", "numitracker"],
        help="Wybierz źródło danych (domyślnie: all)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Pobierz wszystkie wagi i wszystkie źródła",
    )
    args = parser.parse_args()

    weights_to_check = list(WEIGHT_ALIASES.keys()) if args.all else [args.weight]

    for w in weights_to_check:
        all_results: list[dict] = []

        with console.status(f"[bold green]Pobieram dane dla {w}..."):
            if args.source in ("all", "tavex"):
                all_results += scrape_tavex(w)

            if args.source in ("all", "mennica"):
                all_results += scrape_mennica_kapitalowa()

            if args.source in ("all", "numitracker"):
                all_results += scrape_numitracker(w)

        # Jeśli żadne źródło nie zwróciło danych dla tej wagi,
        # dodaj placeholder z URL-ami do ręcznego sprawdzenia
        if not all_results:
            all_results = [
                {
                    "source": "Tavex",
                    "name": f"złote monety {w}",
                    "buy": "sprawdź stronę",
                    "sell": "sprawdź stronę",
                    "url": "https://tavex.pl/zloto/zlote-monety-bulionowe/",
                },
                {
                    "source": "Mennica Kapitałowa",
                    "name": f"złote monety {w}",
                    "buy": "sprawdź stronę",
                    "sell": "sprawdź stronę",
                    "url": "https://mennicakapitalowa.pl/Skup-metali-szlachetnych-cena-odkupu-monet-sztabek-i-zlomu-ccms-pol-32.html",
                },
                {
                    "source": "NumiTracker",
                    "name": f"złote monety {w}",
                    "buy": "sprawdź stronę",
                    "sell": "sprawdź stronę",
                    "url": f"https://numitracker.com/produkty/zloto?metal_form_type=moneta&weight={w}",
                },
            ]

        display_results(all_results, w)


if __name__ == "__main__":
    main()
