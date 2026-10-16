#!/usr/bin/env sh
set -eu
REPO="https://github.com/openchat-oc/OpenChat.git"
APP="$HOME/OpenChat"
say(){ printf '\033[1;35m[OpenChat]\033[0m %s\n' "$*"; }
fail(){ printf '[OpenChat] %s\n' "$*" >&2; exit 1; }
command -v curl >/dev/null 2>&1 || fail "Instala curl y vuelve a intentarlo."
if ! command -v python3 >/dev/null 2>&1 || ! command -v git >/dev/null 2>&1; then
  say "Instalando requisitos del sistema…"
  if command -v pacman >/dev/null 2>&1; then sudo pacman -Sy --needed --noconfirm python python-pip git
  elif command -v apt-get >/dev/null 2>&1; then sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip git
  elif command -v dnf >/dev/null 2>&1; then sudo dnf install -y python3 python3-pip git
  elif command -v zypper >/dev/null 2>&1; then sudo zypper --non-interactive install python3 python3-pip git
  else fail "No reconozco tu gestor de paquetes. Instala Python 3, Git y el módulo venv."; fi
fi
if [ -d "$APP/.git" ]; then say "Actualizando OpenChat…"; git -C "$APP" pull --ff-only
elif [ -e "$APP" ]; then fail "$APP ya existe y no es una instalación Git. Renómbrala primero."
else say "Descargando OpenChat…"; git clone "$REPO" "$APP"; fi
cd "$APP"
python3 -m venv .venv || {
  if command -v pacman >/dev/null 2>&1; then sudo pacman -S --needed --noconfirm python-virtualenv && python3 -m venv .venv
  else fail "No se pudo crear venv. Instala python3-venv (Debian/Ubuntu) y repite."; fi
}
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications"
cat > "$HOME/.local/bin/openchat" <<EOF
#!/bin/sh
exec "$APP/.venv/bin/python" -m app.main "\$@"
EOF
chmod +x "$HOME/.local/bin/openchat"
cat > "$HOME/.local/share/applications/openchat.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=OpenChat
Comment=Asistente de IA de escritorio
Exec=$HOME/.local/bin/openchat
Icon=utilities-terminal
Terminal=false
Categories=Utility;Chat;
StartupNotify=true
EOF
say "Instalación completada. Ejecuta: $HOME/.local/bin/openchat"
say "IA local opcional: instala Ollama y ejecuta ollama pull qwen2.5:1.5b"
