# OpenChat

![Logo de OpenChat](app/logo.svg)

Asistente de chat de escritorio para Linux y Windows. Usa Laguna a través de OpenRouter y tiene una IA local de respaldo con Ollama.

## Incluye
- Interfaz de chat de escritorio con icono propio.
- Configuración de clave OpenRouter desde la app; la clave se guarda solo en el equipo.
- Modelo en la nube: \`poolside/laguna-s-2.1:free\`.
- IA local: Ollama con \`qwen2.5:1.5b\`.
- Instaladores para Linux y Windows que preparan las dependencias de Python, Ollama y el modelo local.
- Desinstalador de OpenChat. Ollama y su modelo se conservan al desinstalar la app.
- No necesita GitHub Releases.

## Linux (CachyOS, Arch, Debian, Ubuntu, Fedora, openSUSE)

Ejecuta:

    curl -fsSL https://raw.githubusercontent.com/openchat-oc/OpenChat/main/install.sh | sh

El instalador comprueba Python y Git, configura un entorno virtual, instala las dependencias de la interfaz, instala Ollama si falta, inicia el servicio e intenta descargar \`qwen2.5:1.5b\`. Necesitas conexión a Internet y espacio libre para el modelo; la instalación puede tardar.

Para desinstalar solo OpenChat:

    ~/.local/bin/openchat-uninstall

Puedes conservar o borrar la clave y configuración. No elimina Ollama ni el modelo.

## Windows

Abre PowerShell y ejecuta:

    irm https://raw.githubusercontent.com/openchat-oc/OpenChat/main/install.ps1 | iex

El instalador usa winget para instalar Python, Git y Ollama si faltan; configura el entorno virtual e intenta descargar \`qwen2.5:1.5b\`.

Para desinstalar OpenChat, ejecuta \`Desinstalar OpenChat.cmd\` desde el Escritorio. Ollama y el modelo local se conservan.

## Primera ejecución

1. Abre OpenChat desde el menú de aplicaciones (Linux) o \`OpenChat.cmd\` (Windows).
2. Para usar Laguna, crea una clave en https://openrouter.ai/settings/keys y añádela desde el botón de configuración.
3. Si OpenRouter no está configurado o falla, OpenChat intenta responder con la IA local Ollama.

La clave API no debe publicarse ni guardarse en el repositorio. Las conversaciones enviadas a OpenRouter salen hacia ese servicio; el modo Ollama usa el servicio local.

## Ejecutar desde el código

    python -m pip install -r requirements.txt
    python -m app.main

## Licencia

MIT