#!/usr/bin/env sh
set -eu
APP="$HOME/OpenChat"
printf '%s\n' "Desinstalador de OpenChat"
printf '%s' "¿Conservar la clave API y configuración? [S/n] "
read ans || ans=""
case "$ans" in n|N|no|NO) rm -rf "$HOME/.config/openchat" ;; *) echo "Se conserva ~/.config/openchat." ;; esac
rm -f "$HOME/.local/bin/openchat" "$HOME/.local/bin/openchat-uninstall" "$HOME/.local/share/applications/openchat.desktop" "$HOME/.local/share/applications/openchat-uninstall.desktop"
rm -rf "$APP"
echo "OpenChat desinstalado. Python, Git, Ollama y otros paquetes del sistema no se han eliminado."
