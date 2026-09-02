# Instalacja Assets (Windows / Linux)

Aplikacja to dashboard Streamlit. Kod jest publiczny na GitHub; **dane portfela są w Dropbox**, nie w repozytorium.

Repo: https://github.com/pmalczak/assets.git  
Skrót: **Assets** tylko na Pulpicie (bez Menu Start / menu aplikacji).

| | Windows | Linux |
|---|---|---|
| Katalog instalacji | `%LOCALAPPDATA%\assets` | `$XDG_DATA_HOME/assets` (domyślnie `~/.local/share/assets`) |
| Instalator | `install/install.ps1` | `install/install.sh` |
| Uruchamianie | `install/launch.bat` | `install/launch.sh` |

## Wymagania przed instalatorem

1. Konto użytkownika i dostęp do sieci (pierwsza instalacja i aktualizacje).
2. **Dropbox** z folderem `INWESTYCJE` zsynchronizowanym na ten komputer, w tym:
   - `Dropbox/INWESTYCJE/assets/a_config.xlsx`
   - katalogi wyciągów (`assets/`, `cash_pool/` itd.)
3. Narzędzia:
   - **Windows 10/11:** `winget` (do ewentualnej instalacji Git). Jeśli nie ma `winget`, zainstaluj Git ręcznie: https://git-scm.com/download/win
   - **Linux:** `bash`, opcjonalnie `sudo` + `apt`/`dnf`/`pacman` (gdy brak Git/curl). Środowisko graficzne potrzebne do skrótu na Pulpicie i przeglądarki Streamlit.

Bez zsynchronizowanego Dropbox dashboard się nie uruchomi poprawnie (`assert` na `INWESTYCJE`). Instalator tylko ostrzeże — nie blokuje setupu.

## Instalacja (goły PC)

### Windows

W PowerShell (nie trzeba Administratora, chyba że `winget`/Git poprosi o UAC):

```powershell
irm https://raw.githubusercontent.com/pmalczak/assets/main/install/install.ps1 | iex
```

Alternatywnie: sklonuj lub pobierz ZIP, wejdź do `install\` i kliknij dwukrotnie `install.bat`.

### Linux

W terminalu:

```bash
curl -fsSL https://raw.githubusercontent.com/pmalczak/assets/main/install/install.sh | bash
```

Alternatywnie: sklonuj repo i uruchom `bash install/install.sh`.

Jeśli Git/curl nie są zainstalowane, one-liner przez rurę może nie umieć zapytać o hasło `sudo` — wtedy `sudo apt install git curl` i ponów, albo pobierz skrypt i uruchom go z terminala.

One-linery działają, gdy dany skrypt jest już na gałęzi `main` na GitHub.

Instalator:

- doinstaluje Git i `uv`, jeśli ich brak;
- sklonuje repo do katalogu instalacji (albo zrobi `git pull --ff-only`, jeśli klon już jest);
- zainstaluje Python 3.13 przez `uv` i zależności (`uv sync`);
- utworzy skrót **Assets** na Pulpicie (`Assets.lnk` / `Assets.desktop`).

## Uruchamianie

Kliknij **Assets** na Pulpicie (Linux: ewentualnie „Allow Launch” / zaufaj plikowi `.desktop`). Z terminala: `bash ~/.local/share/assets/install/launch.sh`.

- **Jest sieć:** `git pull --ff-only`, potem `uv sync`, potem Streamlit.
- **Brak sieci albo pull się nie uda** (np. lokalne zmiany, brak fast-forward): komunikat i start **lokalnej kopii** — bez `git reset --hard`.
- Konsola / terminal zostaje otwarty na czas działania Streamlit.

## Po pierwszym starcie

Katalog `data_steps/` w instalacji jest pusty (cache snapshotów, FX, Yahoo). W UI **przelicz snapshoty**. Raporty oparte o historię pojawią się po tej regeneracji.

## Ponowna instalacja / naprawa

Uruchom ponownie instalator (one-liner albo `install.bat` / `install.sh`). Skrypt jest idempotentny: dociąga brakujące narzędzia, aktualizuje klon przy sieci i odświeża skrót na Pulpicie.

Jeśli katalog instalacji istnieje i **nie** jest klonem tego repo — usuń ten folder i uruchom instalator jeszcze raz.
