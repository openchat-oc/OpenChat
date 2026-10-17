#!/usr/bin/env sh
# Desinstalador de OpenChat. No borra datos personales ni software compartido sin preguntar.
set -eu
APP="$HOME/OpenChat"
DATA="${OPENCHAT_HOME:-$HOME/.config/openchat}"
ask(){
  [ "${OPENCHAT_ASSUME_YES:-0}" = "1" ] && return 0
  if ( : </dev/tty ) 2>/dev/null; then printf '%s [s/N] ' "$1" >/dev/tty; read a </dev/tty || a=""; case "$a" in s|S|si|SI|sí|y|Y) return 0 ;; esac; fi
  return 1
}
cat <<TXT
Desinstalador de OpenChat

SE ELIMINARÁ:   la aplicación ($APP, con su entorno virtual), los lanzadores y el icono.
SE CONSERVARÁ:  Ollama y los modelos descargados (pueden usarlos otras aplicaciones),
                Python, Git y demás paquetes del sistema.
PREGUNTARÉ:     por tus datos personales en $DATA (por separado).
TXT
ask "¿Continuar con la desinstalación?" || { echo "Cancelado: no se ha borrado nada."; exit 0; }

if ask "¿Borrar también tu CLAVE de OpenRouter y la configuración?"; then
  PY="$APP/.venv/bin/python"
  [ -x "$PY" ] && "$PY" -c "import keyring; keyring.delete_password('openchat','openrouter')" >/dev/null 2>&1 || true
  rm -f "$DATA/openrouter.key" "$DATA/settings.json" "$DATA/settings.json.bak" "$DATA/openchat.log"*
  echo "Clave y configuración eliminadas."
else
  echo "Se conservan la clave y la configuración en $DATA."
fi
if ask "¿Borrar también el HISTORIAL de conversaciones?"; then
  rm -f "$DATA/conversations.db" "$DATA/conversation.json" "$DATA/.conversation-imported"
  echo "Historial eliminado."
else
  echo "Se conserva el historial en $DATA."
fi
rmdir "$DATA" 2>/dev/null || true
rm -f "$HOME/.local/bin/openchat" "$HOME/.local/share/applications/openchat.desktop" "$HOME/.local/share/applications/openchat-uninstall.desktop" "$HOME/.local/share/icons/hicolor/scalable/apps/openchat.svg"
rm -rf "$APP"
rm -f "$HOME/.local/bin/openchat-uninstall"
echo "OpenChat desinstalado. Ollama, sus modelos y los paquetes del sistema NO se han tocado."
