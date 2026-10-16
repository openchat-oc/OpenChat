# OpenChat

![Logo de OpenChat](app/logo.svg)

Asistente de IA de escritorio para Linux y Windows. Permite elegir OpenRouter (nube) u Ollama (local); OpenChat no cambia de proveedor en silencio.

## Incluye
- Interfaz de chat de escritorio con icono propio.
- Configuración de clave OpenRouter desde la app; la clave se guarda solo en el equipo.
- Modelo en la nube: \`poolside/laguna-s-2.1:free\`.
- IA local: Ollama con \`qwen2.5:1.5b\`.
- Instaladores para Linux y Windows. Ollama y el modelo local son opcionales para no descargar gigabytes sin permiso.
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
3. La IA local Ollama queda preparada durante la instalación y puede usarse sin clave.
4. Para activar también Laguna en la nube, crea una clave de OpenRouter y añádela desde ⚙. La clave no se puede generar automáticamente y puede estar sujeta a límites o condiciones del proveedor.
5. Al terminar la instalación, OpenChat se abre automáticamente.

La clave API no debe publicarse ni guardarse en el repositorio. Las conversaciones enviadas a OpenRouter salen hacia ese servicio; el modo Ollama usa el servicio local.

## Ejecutar desde el código

    python -m pip install -r requirements.txt
    python -m app.main


## Funcionalidad y limitaciones

- El asistente de configuración permite seleccionar nube o local y persiste el proveedor y el modelo elegidos.
- La conversación usa el proveedor seleccionado sin fallback silencioso.
- El guardado de archivos generados comprueba los nombres, evita sobrescrituras no autorizadas y verifica la escritura.
- El historial persistente, el modo agente con herramientas, el streaming/cancelación y el actualizador transaccional todavía no están implementados como funciones completas. El botón de actualización comprueba el repositorio Git local y no instala automáticamente una actualización.

## Pruebas automatizadas

Desde la raíz del repositorio, con Python instalado, ejecuta:

    python -m unittest discover -s tests -v

Las pruebas añadidas cubren la validación de nombres de archivo, la escritura UTF-8, la protección frente a sobrescrituras accidentales y la sustitución explícita de archivos existentes. No sustituyen las pruebas de interfaz gráfica ni las pruebas reales contra OpenRouter u Ollama.

## Guardado seguro de archivos

Los archivos generados se guardan en la carpeta que elijas. OpenChat rechaza nombres que contengan rutas o nombres especiales, comprueba el contenido escrito y pide confirmación antes de sobrescribir archivos existentes. La ejecución de los archivos generados no es automática.

## Licencia

MIT