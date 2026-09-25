# Instrukcja dla Cursor — odtworzenie pliku z lokalnego, niezacommitowanego repo

Cel: znaleźć i przywrócić kod, który **był zapisany lokalnie**, ale **nigdy nie trafił do Gita / GitHuba** (np. `app/maintenance/prune_contained_statements.py`).

## Kontekst (ten przypadek)

- Plik: `app/maintenance/prune_contained_statements.py` (+ testy)
- Powstał w sesji Cursor, działał lokalnie, opisany w `Cursor_rules.md`
- **Nie był** w `git log` ani na `origin/main`
- Na GitHubie jest teraz na gałęzi **`maintenance`** (po odtworzeniu z transcriptu)

Jeśli na **tej** maszynie masz starą kopię workspace z niezacommitowanymi plikami — użyj ścieżki A.  
Jeśli pliku nie ma na dysku, a był tylko w czacie Cursor — ścieżka B.  
Jeśli wystarczy pobrać z GitHuba — ścieżka C.

---

## A. Przeszukanie lokalnego, niezacommitowanego working tree

Wklej agentowi:

```
Szukam pliku app/maintenance/prune_contained_statements.py (oraz
test_prune_contained_statements.py, test_period_coverage.py).

1. Sprawdź czy istnieje na dysku (find / Glob).
2. git status / git ls-files --others --exclude-standard — czy jest untracked.
3. git diff HEAD -- <ścieżka> — czy jest zmodyfikowany względem HEAD.
4. Jeśli plik jest na dysku (nawet untracked): skopiuj/zachowaj treść,
   zrób gałąź recovery, dodaj do Gita, commit.
5. Nie kasuj lokalnych zmian bez mojej zgody.
```

Komendy pomocnicze:

```bash
find . -name 'prune_contained_statements.py'
git status --short -- '**/prune_contained*'
git ls-files --others --exclude-standard | grep prune
git stash list   # czasem schowane
```

---

## B. Odtworzenie z agent transcripts Cursor (gdy pliku nie ma na dysku)

Cursor trzyma historię tool calls (w tym pełne `Write` / `StrReplace`) w:

- Linux: `~/.cursor/projects/<slug-projektu>/agent-transcripts/<uuid>/<uuid>.jsonl`
- Szukaj też: `~/.cursor/projects/*/agent-transcripts/**/*.jsonl`

Wklej agentowi:

```
Pliku app/maintenance/prune_contained_statements.py nie ma w repo ani w git log.
Odtwórz go z agent transcripts Cursor:

1. rg -l 'prune_contained_statements' ~/.cursor/projects/*/agent-transcripts/
2. W pasującym .jsonl znajdź tool_use Write na tę ścieżkę, potem wszystkie
   StrReplace na ten sam path — odtwórz finalną treść chronologicznie.
3. To samo dla test_prune_contained_statements.py i test_period_coverage.py
   (oraz ewentualnych zmian w period_coverage.py).
4. Zapisz pliki do app/, uruchom:
   PYTHONPATH=app uv run python -m unittest \
     unit_testing.test_prune_contained_statements \
     unit_testing.test_period_coverage -v
5. Pokaż mi diff; nie commituj bez prośby.
```

Uwaga: w nazwie pliku testowego `endswith('prune_contained_statements.py')`
łapie też `test_prune_…` — filtruj po **pełnej** ścieżce / basename.

---

## C. Pobranie z GitHuba (gałąź maintenance)

Jeśli druga maszyna ma czyste repo bez lokalnej kopii:

```bash
git fetch origin maintenance
git checkout maintenance
# albo tylko pliki:
git checkout origin/maintenance -- \
  app/maintenance/prune_contained_statements.py \
  app/unit_testing/test_prune_contained_statements.py \
  app/unit_testing/test_period_coverage.py
```

---

## Weryfikacja

```bash
cd app   # lub PYTHONPATH=app z roota
uv run python -m unittest unit_testing.test_prune_contained_statements \
  unit_testing.test_period_coverage -v
uv run python maintenance/prune_contained_statements.py   # dry-run
```

Skrypt raportuje: pliki zawarte w innych + luki pokrycia; `--delete` kasuje tylko zawarte.

---

## Odpowiedź z drugiej maszyny (Windows, 2026-09-25)

Do pierwotnego agenta / sesji, która zostawiła tę instrukcję:

1. **Ścieżka C wykonana.** Checkout lokalnej `maintenance` z `origin/maintenance` (`d5b3092 Restore prune_contained_statements from local Cursor session`).
2. Pliki na dysku i w Gicie:
   - `app/maintenance/prune_contained_statements.py`
   - `app/unit_testing/test_prune_contained_statements.py`
   - `app/unit_testing/test_period_coverage.py`
3. **Weryfikacja OK:** `unittest` — 18 testów passed.
4. Dry-run: **22** pliki zawarte (do usunięcia), **0** luk; **bez** `--delete`.
5. Na Windows konsola cp1250 wywala dry-run na znaku `⊂` — działa z `PYTHONIOENCODING=utf-8`.
6. Reguły zaktualizowane: sync z GitHubem także dla **`maintenance`** (nie tylko `main`) — `.cursor/rules/git-sync-github.mdc` + `Cursor_rules.md`.
7. Dalsze odtwarzanie ze ścieżki A/B **niepotrzebne** na tej maszynie.
