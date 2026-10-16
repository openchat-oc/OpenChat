#!/usr/bin/env sh
set -eu
REPO="https://github.com/openchat-oc/OpenChat.git"
APP="$HOME/OpenChat"
BIN="$HOME/.local/bin"
APPS="$HOME/.local/share/applications"
say(){ printf '\033[1;35m[OpenChat]\033[0m %s\n' "$*"; }
fail(){ printf '[OpenChat] %s\n' "$*" >&2; exit 1; }
has(){ command -v "$1" >/dev/null 2>&1; }
install_pkgs(){
  if [ "$(id -u)" -ne 0 ] && ! has sudo; then fail "Hace falta sudo para instalar dependencias del sistema."; fi
  if has pacman; then sudo pacman -Sy --needed --noconfirm "$@"
  elif has apt-get; then sudo apt-get update && sudo apt-get install -y "$@"
  elif has dnf; then sudo dnf install -y "$@"
  elif has zypper; then sudo zypper --non-interactive install "$@"
  else fail "No reconozco el gestor de paquetes. Instala manualmente: $*"; fi
}
has curl || fail "Necesitas curl para descargar OpenChat."
if ! has python3 || ! has git; then
  say "Instalando Python 3, Git y herramientas necesarias…"
  if has pacman; then install_pkgs python python-pip git
  elif has apt-get; then install_pkgs python3 python3-venv python3-pip git
  elif has dnf; then install_pkgs python3 python3-pip git
  elif has zypper; then install_pkgs python3 python3-pip git
  else fail "Instala Python 3 y Git y vuelve a ejecutar."; fi
fi
if [ -d "$APP/.git" ]; then
  say "Actualizando OpenChat…"
  git -C "$APP" pull --ff-only
elif [ -e "$APP" ]; then
  fail "$APP existe y no es una instalación Git. Muévelo o renómbralo antes de continuar."
else
  say "Descargando OpenChat…"
  git clone "$REPO" "$APP"
fi
cd "$APP"
if ! python3 -m venv .venv 2>/dev/null; then
  if has pacman; then install_pkgs python-virtualenv
  elif has apt-get; then install_pkgs python3-venv
  else fail "No pude crear el entorno virtual. Instala el paquete venv de tu distribución."; fi
  python3 -m venv .venv
fi
say "Instalando dependencias Python en un entorno aislado…"
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
mkdir -p "$BIN" "$APPS"
cat > "$BIN/openchat" <<EOF
#!/usr/bin/env sh
exec "$APP/.venv/bin/python" -m app.main "\$@"
EOF
chmod +x "$BIN/openchat"
cat > "$BIN/openchat-uninstall" <<'EOF'
#!/usr/bin/env sh
set -eu
APP="$HOME/OpenChat"
printf '%s\n' "Esto eliminará OpenChat, su entorno virtual y sus lanzadores."
printf '%s' "¿Conservar la clave API y configuración? [S/n] "
read ans || ans=""
case "$ans" in n|N|no|NO) rm -rf "$HOME/.config/openchat" ;; *) echo "Se conserva ~/.config/openchat." ;; esac
rm -f "$HOME/.local/bin/openchat" "$HOME/.local/bin/openchat-uninstall" "$HOME/.local/share/applications/openchat.desktop" "$HOME/.local/share/applications/openchat-uninstall.desktop"
rm -rf "$APP"
echo "OpenChat desinstalado. No se eliminó Python, Git, Ollama ni ningún otro paquete del sistema."
EOF
chmod +x "$BIN/openchat-uninstall"
cat > "$APPS/openchat.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=OpenChat
Comment=Asistente de IA de escritorio
Exec=$BIN/openchat
Icon=utilities-terminal
Terminal=false
Categories=Utility;Chat;
StartupNotify=true
EOF
cat > "$APPS/openchat-uninstall.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Desinstalar OpenChat
Comment=Eliminar OpenChat de este usuario
Exec=$BIN/openchat-uninstall
Icon=edit-delete
Terminal=true
Categories=Utility;
EOF
say "Instalación completada. OpenChat aparece en el menú de aplicaciones."
say "Iniciar desde terminal: $BIN/openchat"
say "Desinstalar: $BIN/openchat-uninstall"
say "Ollama es opcional y no se instala ni se elimina automáticamente."
