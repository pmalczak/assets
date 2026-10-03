#!/usr/bin/env bash
# Uruchamia Assets: przy sieci git pull + uv sync, potem Streamlit.

set -eu

MANAGED_INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/assets"
INSTALL_DIR="$MANAGED_INSTALL_DIR"

if [[ -n "${BASH_SOURCE[0]:-}" ]]; then
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  from_script="$(cd "$script_dir/.." && pwd)"
  if [[ -d "$from_script/.git" ]]; then
    INSTALL_DIR="$from_script"
  fi
fi

step() { printf '\n\033[36m==> %s\033[0m\n' "$1"; }
ok() { printf '\033[32mOK  %s\033[0m\n' "$1"; }
warn() { printf '\033[33mUWAGA  %s\033[0m\n' "$1"; }
die() { printf '\n\033[31mBLAD: %s\033[0m\n' "$1" >&2; exit 1; }

# Instalacja ze skrótu / XDG — wolno nadpisać lokalne zmiany.
# Klon developerski (inny katalog) — tylko ostrożny pull --ff-only.
is_managed_install() {
  local a b
  [[ -d "$MANAGED_INSTALL_DIR" ]] || return 1
  a="$(cd "$INSTALL_DIR" && pwd -P)"
  b="$(cd "$MANAGED_INSTALL_DIR" && pwd -P)"
  [[ "$a" == "$b" ]]
}

refresh_path() {
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1
}

github_online() {
  if need_cmd curl; then
    curl -fsI --max-time 5 https://github.com >/dev/null 2>&1
  elif need_cmd wget; then
    wget -q --spider --timeout=5 https://github.com >/dev/null 2>&1
  else
    return 1
  fi
}

update_from_github() {
  if ! github_online; then
    warn "Brak sieci - uruchamiam lokalna kopie"
    return
  fi
  step "Aktualizacja z GitHub"
  if is_managed_install; then
    # Instalacja użytkowa: lokalne edycje nie mogą blokować update.
    # -f odrzuca zmiany w tracked files; data_steps (gitignore) zostaje.
    if git -C "$INSTALL_DIR" fetch origin \
      && git -C "$INSTALL_DIR" checkout -f -B main origin/main; then
      ok "git checkout -f main ← origin/main (instalacja zarzadzana)"
    else
      warn "Aktualizacja instalacji (fetch/checkout main) nie powiodla sie. Startuje lokalna kopia."
      return
    fi
  else
    if git -C "$INSTALL_DIR" pull --ff-only; then
      ok "git pull --ff-only (klon developerski)"
    else
      warn "git pull --ff-only nie powiodl sie (konflikt albo lokalne zmiany). Startuje lokalna kopia — w klonie developerskim bez reset --hard."
      return
    fi
  fi
  step "uv sync"
  if (cd "$INSTALL_DIR" && uv sync); then
    ok "uv sync"
  else
    warn "uv sync nie powiodl sie - startuje lokalna kopia"
  fi
}

start_assets_app() {
  local app_dir script
  app_dir="$INSTALL_DIR/app"
  script="$app_dir/app_assets.py"
  if [[ ! -f "$script" ]]; then
    die "Brak $script - instalacja jest niepelna. Uruchom install/install.sh."
  fi
  step "Streamlit ($script)"
  cd "$app_dir"
  exec uv run streamlit run app_assets.py
}

refresh_path

if [[ ! -d "$INSTALL_DIR/.git" ]]; then
  die "Brak klonu w $INSTALL_DIR. Uruchom najpierw install/install.sh."
fi
if ! need_cmd git; then
  die "Brak Git w PATH. Uruchom instalator ponownie."
fi
if ! need_cmd uv; then
  die "Brak uv w PATH. Uruchom instalator ponownie."
fi

update_from_github
start_assets_app
