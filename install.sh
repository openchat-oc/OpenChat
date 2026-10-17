#!/usr/bin/env sh
set -eu
REPO="https://github.com/openchat-oc/OpenChat.git"
APP="$HOME/OpenChat"
BIN="$HOME/.local/bin"
APPS="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
MODEL="qwen2.5:1.5b"
# Pick a conservative model size from physical RAM and CPU count.
if [ -r /proc/meminfo ]; then
  RAM_KB=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)
  CORES=$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)
  if [ "${RAM_KB:-0}" -lt 6291456 ] || [ "${CORES:-2}" -le 2 ]; then
    MODEL="qwen2.5:0.5b"
  elif [ "${RAM_KB:-0}" -gt 10485760 ]; then
    MODEL="qwen2.5:3b"
  fi
fi
say(){ printf '\033[1;35m[OpenChat]\033[0m %s\n' "$*"; }
fail(){ printf '[OpenChat] %s\n' "$*" >&2; exit 1; }
has(){ command -v "$1" >/dev/null 2>&1; }
root_run(){ if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi; }
install_pkgs(){
  if [ "$(id -u)" -ne 0 ] && ! has sudo; then fail "Hace falta sudo para instalar dependencias del sistema."; fi
  if has pacman; then root_run pacman -S --needed --noconfirm "$@"
  elif has apt-get; then root_run apt-get update && root_run apt-get install -y "$@"
  elif has dnf; then root_run dnf install -y "$@"
  elif has zypper; then root_run zypper --non-interactive install "$@"
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
  say "Actualizando OpenChat…"; git -C "$APP" pull --ff-only
elif [ -e "$APP" ]; then
  fail "$APP existe y no es una instalación Git. Muévelo o renómbralo antes de continuar."
else
  say "Descargando OpenChat…"; git clone "$REPO" "$APP"
fi
cd "$APP"
if ! python3 -m venv .venv 2>/dev/null; then
  if has pacman; then install_pkgs python-virtualenv
  elif has apt-get; then install_pkgs python3-venv
  else fail "No pude crear el entorno virtual. Instala el paquete venv de tu distribución."; fi
  python3 -m venv .venv
fi
say "Instalando dependencias de la aplicación…"
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
mkdir -p "$BIN" "$APPS" "$ICON_DIR"
cp "$APP/app/logo.svg" "$ICON_DIR/openchat.svg"
cat > "$BIN/openchat" <<EOF
#!/usr/bin/env sh
exec "$APP/.venv/bin/python" -m app.main "\$@"
EOF
chmod +x "$BIN/openchat"
cat > "$BIN/openchat-uninstall" <<'EOF'
#!/usr/bin/env sh
set -eu
APP="$HOME/OpenChat"
printf '%s\n' "Esto eliminará OpenChat, su entorno virtual, lanzadores e icono."
printf '%s' "¿Conservar la clave API y configuración? [S/n] "
read ans || ans=""
case "$ans" in n|N|no|NO) rm -rf "$HOME/.config/openchat" ;; *) echo "Se conserva ~/.config/openchat." ;; esac
rm -f "$HOME/.local/bin/openchat" "$HOME/.local/bin/openchat-uninstall" "$HOME/.local/share/applications/openchat.desktop" "$HOME/.local/share/applications/openchat-uninstall.desktop" "$HOME/.local/share/icons/hicolor/scalable/apps/openchat.svg"
rm -rf "$APP"
echo "OpenChat desinstalado. Ollama y el modelo local se conservan."
EOF
chmod +x "$BIN/openchat-uninstall"
cat > "$APPS/openchat.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=OpenChat
Comment=Asistente de IA de escritorio
Exec=$BIN/openchat
Icon=$ICON_DIR/openchat.svg
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
if [ "${OPENCHAT_INSTALL_OLLAMA:-0}" = "1" ]; then
  say "Preparando la IA local Ollama…"
  if ! has ollama; then
    if ! curl -fsSL https://ollama.com/install.sh | sh; then
      fail "No se pudo instalar Ollama. Revisa la conexión y vuelve a ejecutar este instalador."
    fi
  fi
  has ollama || fail "Ollama no quedó instalado correctamente."
  if has systemctl; then root_run systemctl enable --now ollama >/dev/null 2>&1 || true; fi
  if ! curl -fsS --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    say "Iniciando el servicio local de Ollama…"
    nohup ollama serve >/tmp/openchat-ollama.log 2>&1 &
    tries=0
    while [ "$tries" -lt 20 ]; do
      if curl -fsS --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then break; fi
      sleep 1; tries=$((tries+1))
    done
  fi
  curl -fsS --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1 || fail "Ollama está instalado pero no responde en localhost:11434."
  say "Descargando el modelo local $MODEL (puede ocupar alrededor de 1 GB o más)…"
  ollama pull "$MODEL" || fail "Ollama funciona, pero no se pudo descargar $MODEL. Repite: ollama pull $MODEL"
else
  say "Instalación nube preparada. Ollama y el modelo local se omiten para ahorrar espacio."
  say "Para incluir Ollama, ejecuta de nuevo: curl -fsSL https://raw.githubusercontent.com/openchat-oc/OpenChat/main/install.sh | env OPENCHAT_INSTALL_OLLAMA=1 sh"
fi
say "Instalación de OpenChat completada."
say "Iniciar: $BIN/openchat"
say "Desinstalar OpenChat: $BIN/openchat-uninstall"
say "El desinstalador no elimina Ollama ni el modelo descargado."
say "Abriendo OpenChat…"
"$BIN/openchat" >/tmp/openchat-app.log 2>&1 &
