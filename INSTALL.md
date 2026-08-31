# Instalacja Assets na nowym Windows

Aplikacja to dashboard Streamlit. Kod jest publiczny na GitHub; **dane portfela są w Dropbox**, nie w repozytorium.

Repo: https://github.com/pmalczak/assets.git  
Katalog instalacji: `%LOCALAPPDATA%\assets`  
Skrót: **Assets** tylko na Pulpicie (bez Menu Start).

## Wymagania przed instalatorem

1. Konto Windows i dostęp do sieci (pierwsza instalacja i aktualizacje).
2. **Dropbox** z folderem `INWESTYCJE` zsynchronizowanym na ten komputer, w tym:
   - `Dropbox\INWESTYCJE\assets\a_config.xlsx`
   - katalogi wyciągów (`assets\`, `cash_pool\` itd.)
3. Windows 10/11 z `winget` (do ewentualnej instalacji Git). Jeśli nie ma `winget`, zainstaluj Git ręcznie: https://git-scm.com/download/win

Bez zsynchronizowanego Dropbox dashboard się nie uruchomi poprawnie (`assert` na `INWESTYCJE`). Instalator tylko ostrzeże — nie blokuje setupu.

## Instalacja (goły PC)

W PowerShell (nie trzeba Administratora, chyba że `winget`/Git poprosi o UAC):

```powershell
irm https://raw.githubusercontent.com/pmalczak/assets/main/install/install.ps1 | iex
```

Ten one-liner zadziała dopiero gdy `install/install.ps1` jest już na gałęzi `main` na GitHub.

Alternatywnie: sklonuj lub pobierz ZIP, wejdź do `install\` i kliknij dwukrotnie `install.bat`.

Instalator:

- doinstaluje Git i `uv`, jeśli ich brak;
- sklonuje repo do `%LOCALAPPDATA%\assets` (albo zrobi `git pull --ff-only`, jeśli klon już jest);
- zainstaluje Python 3.13 przez `uv` i zależności (`uv sync`);
- utworzy skrót **Assets** na Pulpicie.

## Uruchamianie

Kliknij **Assets** na Pulpicie.

- **Jest sieć:** `git pull --ff-only`, potem `uv sync`, potem Streamlit.
- **Brak sieci albo pull się nie uda** (np. lokalne zmiany, brak fast-forward): komunikat i start **lokalnej kopii** — bez `git reset --hard`.
- Konsola zostaje otwarta na czas działania Streamlit.

## Po pierwszym starcie

Katalog `data_steps\` w instalacji jest pusty (cache snapshotów, FX, Yahoo). W UI **przelicz snapshoty**. Raporty oparte o historię pojawią się po tej regeneracji.

## Ponowna instalacja / naprawa

Uruchom ponownie `install.ps1` (one-liner albo `install.bat`). Skrypt jest idempotentny: dociąga brakujące narzędzia, aktualizuje klon przy sieci i odświeża skrót na Pulpicie.

Jeśli `%LOCALAPPDATA%\assets` istnieje i **nie** jest klonem tego repo — usuń ten folder i uruchom instalator jeszcze raz.
