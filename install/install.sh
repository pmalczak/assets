#!/usr/bin/env bash
# Jednorazowa instalacja assets na Linux.
# Bootstrap (nowy PC): curl -fsSL https://raw.githubusercontent.com/pmalczak/assets/main/install/install.sh | bash

set -eu

REPO_URL="https://github.com/pmalczak/assets.git"
INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/assets"
PYTHON_VERSION="3.13"
SHORTCUT_NAME="Assets.desktop"

step() { printf '\n\033[36m==> %s\033[0m\n' "$1"; }
ok() { printf '\033[32mOK  %s\033[0m\n' "$1"; }
warn() { printf '\033[33mUWAGA  %s\033[0m\n' "$1"; }
die() { printf '\n\033[31mBLAD: %s\033[0m\n' "$1" >&2; exit 1; }

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

normalize_git_url() {
  local n
  n="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  n="${n%/}"
  n="${n%.git}"
  printf '%s' "$n"
}

install_pkg() {
  local pkg="$1"
  if need_cmd apt-get; then
    sudo apt-get update
    sudo apt-get install -y "$pkg"
  elif need_cmd dnf; then
    sudo dnf install -y "$pkg"
  elif need_cmd pacman; then
    sudo pacman -S --noconfirm "$pkg"
  else
    return 1
  fi
}

install_git_if_missing() {
  if need_cmd git; then
    ok "Git juz jest"
    return
  fi
  step "Instalacja Git"
  if install_pkg git && need_cmd git; then
    ok "Git zainstalowany"
    return
  fi
  die "Brak Git. Zainstaluj recznie, np.: sudo apt install git"
}

install_curl_if_missing() {
  if need_cmd curl || need_cmd wget; then
    return
  fi
  step "Instalacja curl"
  if install_pkg curl && need_cmd curl; then
    ok "curl zainstalowany"
    return
  fi
  die "Brak curl. Zainstaluj recznie, np.: sudo apt install curl"
}

install_uv_if_missing() {
  if need_cmd uv; then
    ok "uv juz jest"
    return
  fi
  step "Instalacja uv"
  if need_cmd curl; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
  elif need_cmd wget; then
    wget -qO- https://astral.sh/uv/install.sh | sh
  else
    die "Nie udalo sie zainstalowac uv (brak curl/wget)."
  fi
  refresh_path
  if ! need_cmd uv; then
    die "uv zainstalowane, ale nie jest w PATH. Zamknij terminal i uruchom instalator ponownie."
  fi
  ok "uv zainstalowane"
}

install_repo_clone() {
  step "Repozytorium w $INSTALL_DIR"
  local want have
  want="$(normalize_git_url "$REPO_URL")"
  if [[ -d "$INSTALL_DIR/.git" ]]; then
    have="$(normalize_git_url "$(git -C "$INSTALL_DIR" remote get-url origin 2>/dev/null || true)")"
    if [[ "$have" != "$want" ]]; then
      die "Katalog $INSTALL_DIR to inne repo ($have). Usun go albo wskaz inny folder."
    fi
    if github_online; then
      if git -C "$INSTALL_DIR" pull --ff-only; then
        ok "git pull --ff-only"
      else
        warn "git pull nie powiodl sie - zostaje lokalna kopia"
      fi
    else
      warn "Brak sieci - pomijam git pull"
    fi
    return
  fi
  if [[ -e "$INSTALL_DIR" ]]; then
    if [[ -d "$INSTALL_DIR" ]] && [[ -z "$(ls -A "$INSTALL_DIR" 2>/dev/null || true)" ]]; then
      :
    else
      die "Katalog $INSTALL_DIR istnieje i nie jest klonem git. Usun go i uruchom instalator ponownie."
    fi
  fi
  git clone "$REPO_URL" "$INSTALL_DIR"
  ok "Sklonowano $REPO_URL"
}

install_python_env() {
  step "Python $PYTHON_VERSION + zaleznosci (uv)"
  (
    cd "$INSTALL_DIR"
    uv python install "$PYTHON_VERSION"
    uv sync
  )
  ok "Srodowisko gotowe"
}

check_dropbox_config() {
  local config="$HOME/Dropbox/INWESTYCJE/assets/a_config.xlsx"
  if [[ -f "$config" ]]; then
    ok "Znaleziono $config"
  else
    warn "Brak $config. Zsynchronizuj Dropbox (folder INWESTYCJE) zanim uruchomisz dashboard."
  fi
}

desktop_dir() {
  local d=""
  if need_cmd xdg-user-dir; then
    d="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
  fi
  if [[ -n "$d" && -d "$d" ]]; then
    printf '%s' "$d"
    return
  fi
  if [[ -d "$HOME/Desktop" ]]; then
    printf '%s' "$HOME/Desktop"
    return
  fi
  if [[ -d "$HOME/Pulpit" ]]; then
    printf '%s' "$HOME/Pulpit"
    return
  fi
  printf '%s' "$HOME/Desktop"
}

install_desktop_shortcut() {
  step "Skrot na Pulpicie"
  local target desktop lnk
  target="$INSTALL_DIR/install/launch.sh"
  if [[ ! -f "$target" ]]; then
    die "Brak $target - klon repozytorium jest niepelny (brak install/launch.sh na GitHub)."
  fi
  chmod +x "$target" "$INSTALL_DIR/install/install.sh" 2>/dev/null || true
  desktop="$(desktop_dir)"
  mkdir -p "$desktop"
  lnk="$desktop/$SHORTCUT_NAME"
  cat > "$lnk" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Assets
Comment=Assets Dashboard
Exec=bash "$target"
Path=$INSTALL_DIR
Terminal=true
StartupNotify=true
EOF
  chmod +x "$lnk"
  if need_cmd gio; then
    gio set "$lnk" metadata::trusted true 2>/dev/null || true
  fi
  ok "Skrot: $lnk (bez menu aplikacji)"
}

refresh_path
install_git_if_missing
install_curl_if_missing
refresh_path
install_uv_if_missing
install_repo_clone
install_python_env
check_dropbox_config
install_desktop_shortcut
printf '\n\033[32mInstalacja zakonczona. Uruchom Assets ze skrotu na Pulpicie.\033[0m\n'
