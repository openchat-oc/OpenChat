#!/usr/bin/env sh
# Instalador de OpenChat para Linux (CachyOS/Arch, Debian/Ubuntu, Fedora, openSUSE).
#   curl -fsSL https://raw.githubusercontent.com/openchat-oc/OpenChat/main/install.sh | sh
#
# Variables opcionales (se pasan con:  curl ... | env VAR=valor sh):
#   OPENCHAT_INSTALL_OLLAMA=1   instala también Ollama y descarga el modelo local (por defecto se omite)
#   OPENCHAT_MODEL=qwen2.5:1.5b modelo local a descargar
#   OPENCHAT_ASSUME_YES=1       no preguntar nada (para instalaciones desatendidas)
#   OPENCHAT_BRANCH=main        rama a instalar          OPENCHAT_REPO=<url>  repositorio alternativo
set -eu

REPO="${OPENCHAT_REPO:-https://github.com/openchat-oc/OpenChat.git}"
BRANCH="${OPENCHAT_BRANCH:-main}"
APP="$HOME/OpenChat"
BIN="$HOME/.local/bin"
APPS="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
MODEL="${OPENCHAT_MODEL:-qwen2.5:1.5b}"
OS_RELEASE="${OPENCHAT_OS_RELEASE:-/etc/os-release}"

say(){ printf '\033[1;35m[OpenChat]\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m[OpenChat] Aviso:\033[0m %s\n' "$*" >&2; }
fail(){ printf '\033[1;31m[OpenChat] Error:\033[0m %s\n' "$*" >&2; exit 1; }
has(){ command -v "$1" >/dev/null 2>&1; }

# Pregunta sí/no. Sin terminal y sin OPENCHAT_ASSUME_YES devuelve «no» (nunca decide por ti).
ask(){
  [ "${OPENCHAT_ASSUME_YES:-0}" = "1" ] && return 0
  if ( : </dev/tty ) 2>/dev/null; then
    printf '%s [s/N] ' "$1" >/dev/tty; read ans </dev/tty || ans=""
    case "$ans" in s|S|si|SI|sí|y|Y|yes) return 0 ;; esac
  fi
  return 1
}

# ---- distribución y gestor de paquetes -------------------------------------------------------
distro_ids(){ [ -r "$OS_RELEASE" ] && (. "$OS_RELEASE"; printf '%s %s' "${ID:-}" "${ID_LIKE:-}") || true; }
detect_pm(){
  ids=" $(distro_ids) "
  case "$ids" in
    *" arch "*|*" cachyos "*|*" manjaro "*|*" endeavouros "*) has pacman && { echo pacman; return; } ;;
    *" debian "*|*" ubuntu "*|*" linuxmint "*|*" pop "*) has apt-get && { echo apt; return; } ;;
    *" fedora "*|*" rhel "*|*" centos "*) has dnf && { echo dnf; return; } ;;
    *" suse "*|*" opensuse"*) has zypper && { echo zypper; return; } ;;
  esac
  for pm in pacman apt-get dnf zypper; do has "$pm" && { [ "$pm" = apt-get ] && echo apt || echo "$pm"; return; }; done
  echo none
}
PM="$(detect_pm)"

# Paquetes (nombres reales por familia). Qt6/PySide6 necesita estas bibliotecas del sistema para el plugin xcb.
base_pkgs(){ case "$PM" in
  pacman) echo "python python-pip git curl" ;;
  apt)    echo "python3 python3-venv python3-pip git curl" ;;
  dnf)    echo "python3 python3-pip git curl" ;;
  zypper) echo "python3 python3-pip git curl" ;;
esac; }
qt_pkgs(){ case "$PM" in
  pacman) echo "xcb-util-cursor libxkbcommon-x11 xcb-util-wm xcb-util-image xcb-util-keysyms xcb-util-renderutil libglvnd" ;;
  apt)    echo "libxcb-cursor0 libegl1 libgl1 libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0" ;;
  dnf)    echo "xcb-util-cursor libxkbcommon-x11 xcb-util-wm xcb-util-image xcb-util-keysyms xcb-util-renderutil mesa-libEGL mesa-libGL" ;;
  zypper) echo "libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0 Mesa-libEGL1 Mesa-libGL1" ;;
esac; }

SUDO_EXPLAINED=0
as_root(){
  if [ "$(id -u)" -eq 0 ]; then "$@"
  elif has sudo; then
    if [ "$SUDO_EXPLAINED" = 0 ]; then say "Necesito permisos de administrador SOLO para instalar paquetes del sistema (sudo te lo pedirá)."; SUDO_EXPLAINED=1; fi
    sudo "$@"
  else fail "Hace falta instalar paquetes del sistema y no hay sudo. Instala manualmente: $*"; fi
}
pkg_install(){
  case "$PM" in
    pacman) as_root pacman -S --needed --noconfirm "$@" ;;          # sin -Sy: nunca actualizaciones parciales
    apt)    as_root apt-get update -qq && as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y "$@" ;;
    dnf)    as_root dnf install -y "$@" ;;
    zypper) as_root zypper --non-interactive install "$@" ;;
    *)      fail "No reconozco el gestor de paquetes. Instala manualmente: $*" ;;
  esac
}
pkg_installed(){
  case "$PM" in
    pacman) pacman -Qi "$1" >/dev/null 2>&1 ;;
    apt)    dpkg -s "$1" >/dev/null 2>&1 ;;
    dnf|zypper) rpm -q "$1" >/dev/null 2>&1 ;;
    *) return 1 ;;
  esac
}
missing_pkgs(){ for p in $1; do pkg_installed "$p" || printf '%s ' "$p"; done; }
python_ok(){ has python3 && python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; }

# Permite cargar las funciones para pruebas sin instalar nada.
[ "${OPENCHAT_SOURCE_ONLY:-0}" = "1" ] && return 0 2>/dev/null || true
[ "${OPENCHAT_SOURCE_ONLY:-0}" = "1" ] && exit 0

[ "$(id -u)" -eq 0 ] && [ "${OPENCHAT_ALLOW_ROOT:-0}" != "1" ] && warn "Estás ejecutando como root: OpenChat se instalará en el HOME de root. Lo normal es ejecutarlo con tu usuario."
say "Sistema: $(distro_ids | awk '{print $1}') · gestor de paquetes: $PM"
has curl || has git || [ "$PM" != none ] || fail "Necesitas curl o git para descargar OpenChat."

# ---- dependencias del sistema (solo se instala lo que falta) ----------------------------------
need=""
python_ok || need="$need $(base_pkgs)"
has git   || need="$need git"
has curl  || need="$need curl"
[ "$PM" = apt ] && ! python3 -c 'import venv, ensurepip' 2>/dev/null && need="$need python3-venv python3-pip"
need="$need $(missing_pkgs "$(qt_pkgs)")"
need="$(printf '%s\n' $need | sort -u | tr '\n' ' ')"
if [ -n "$(echo "$need" | tr -d ' ')" ]; then
  say "Faltan paquetes del sistema: $need"
  pkg_install $need
else
  say "Dependencias del sistema: todo presente."
fi
python_ok || fail "Hace falta Python 3.9 o superior (encontrado: $(python3 --version 2>&1 || echo ninguno))."

# ---- código ----------------------------------------------------------------------------------
if [ -d "$APP/.git" ]; then
  say "OpenChat ya está instalado: actualizando (tu configuración e historial no se tocan)…"
  if [ -n "$(git -C "$APP" status --porcelain)" ]; then
    warn "Hay cambios locales en $APP; no actualizo el código para no perderlos."
  else
    git -C "$APP" fetch -q origin "$BRANCH" && git -C "$APP" checkout -q "$BRANCH" 2>/dev/null || true
    git -C "$APP" pull --ff-only -q origin "$BRANCH" || warn "No se pudo actualizar con git; continúo con la versión instalada."
  fi
elif [ -e "$APP" ]; then
  fail "$APP existe y no es una instalación Git. Muévelo o renómbralo antes de continuar."
else
  say "Descargando OpenChat ($BRANCH)…"
  git clone -q --branch "$BRANCH" "$REPO" "$APP"
fi
cd "$APP"

# ---- entorno Python aislado ------------------------------------------------------------------
[ -x .venv/bin/python ] || python3 -m venv .venv || fail "No pude crear el entorno virtual (¿falta el paquete venv de tu distribución?)."
say "Instalando dependencias de la aplicación…"
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r requirements.txt || fail "Falló la instalación de dependencias de Python. Revisa tu conexión y repite."
if ! QT_QPA_PLATFORM=offscreen .venv/bin/python -c 'from PySide6.QtWidgets import QApplication; QApplication([])' 2>/tmp/openchat-qt-check.log; then
  warn "PySide6 se instaló, pero Qt no arranca (faltan bibliotecas del sistema). Detalle en /tmp/openchat-qt-check.log"
  tail -n 3 /tmp/openchat-qt-check.log >&2 || true
else
  say "Comprobación de Qt: correcta."
fi

# ---- lanzadores ------------------------------------------------------------------------------
mkdir -p "$BIN" "$APPS" "$ICON_DIR"
cp "$APP/app/logo.svg" "$ICON_DIR/openchat.svg"
cat > "$BIN/openchat" <<LAUNCH
#!/usr/bin/env sh
cd "$APP" && exec "$APP/.venv/bin/python" -m app.main "\$@"
LAUNCH
chmod +x "$BIN/openchat"
cp "$APP/uninstall.sh" "$BIN/openchat-uninstall"; chmod +x "$BIN/openchat-uninstall"
cat > "$APPS/openchat.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=OpenChat
Comment=Asistente de IA de escritorio
Exec=$BIN/openchat
Icon=$ICON_DIR/openchat.svg
Terminal=false
Categories=Utility;Chat;
StartupNotify=true
DESKTOP
cat > "$APPS/openchat-uninstall.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Desinstalar OpenChat
Comment=Eliminar OpenChat de este usuario
Exec=$BIN/openchat-uninstall
Icon=edit-delete
Terminal=true
Categories=Utility;
DESKTOP
case ":$PATH:" in *":$BIN:"*) ;; *) warn "$BIN no está en tu PATH. Añádelo (bash/zsh: export PATH=\"\$HOME/.local/bin:\$PATH\"; fish: fish_add_path ~/.local/bin) o abre OpenChat desde el menú de aplicaciones." ;; esac

# ---- IA local (opcional) ---------------------------------------------------------------------
want_ollama=0
if [ "${OPENCHAT_INSTALL_OLLAMA:-}" = "1" ]; then want_ollama=1
elif [ -z "${OPENCHAT_INSTALL_OLLAMA:-}" ] && ask "¿Instalar también la IA local (Ollama + modelo $MODEL, ~1 GB o más de descarga)?"; then want_ollama=1; fi
if [ "$want_ollama" = 1 ]; then
  ram_kb="$(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)"
  if [ "${ram_kb:-0}" -gt 0 ] && [ "$ram_kb" -lt 4000000 ]; then
    warn "Tienes menos de 4 GB de RAM: un modelo local puede ir muy lento. El modo nube (OpenRouter) funciona igual de bien."
    ask "¿Continuar con la IA local de todos modos?" || want_ollama=0
  fi
fi
if [ "$want_ollama" = 1 ]; then
  if ! has ollama; then
    if [ "$PM" = pacman ]; then say "Instalando Ollama desde los repositorios oficiales de tu distribución…"; pkg_install ollama
    else
      say "Instalando Ollama con su instalador oficial (https://ollama.com/install.sh). Es un script remoto: si no confías en él, cancela y usa tu gestor de paquetes."
      curl -fsSL https://ollama.com/install.sh | sh || fail "No se pudo instalar Ollama. Instálalo desde https://ollama.com/download y repite con OPENCHAT_INSTALL_OLLAMA=1."
    fi
  fi
  has ollama || fail "Ollama no quedó instalado correctamente."
  has systemctl && as_root systemctl enable --now ollama >/dev/null 2>&1 || true
  up(){ curl -fsS --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; }
  if ! up; then
    say "Iniciando el servicio local de Ollama…"
    nohup ollama serve >/tmp/openchat-ollama.log 2>&1 &
    i=0; while [ "$i" -lt 20 ] && ! up; do sleep 1; i=$((i+1)); done
  fi
  up || fail "Ollama está instalado pero no responde en 127.0.0.1:11434 (log: /tmp/openchat-ollama.log)."
  say "Descargando el modelo local $MODEL…"
  ollama pull "$MODEL" || fail "Ollama funciona, pero no se pudo descargar $MODEL. Repite: ollama pull $MODEL"
  say "IA local lista: Ollama responde y el modelo $MODEL está descargado."
else
  say "IA local omitida (modo nube). Cuando la quieras: curl -fsSL https://raw.githubusercontent.com/openchat-oc/OpenChat/main/install.sh | env OPENCHAT_INSTALL_OLLAMA=1 sh"
fi

say "Instalación de OpenChat completada."
say "Abrir: openchat   (o desde el menú de aplicaciones)"
say "Desinstalar: openchat-uninstall   (te dirá qué conserva y qué borra)"
if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then say "Abriendo OpenChat…"; ( "$BIN/openchat" >/tmp/openchat-app.log 2>&1 & ); else say "No detecto un entorno gráfico; abre OpenChat más tarde con: openchat"; fi
