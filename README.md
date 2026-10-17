# OpenChat

![Logo de OpenChat](app/logo.svg)

Asistente de IA de escritorio para Linux y Windows. Incluye chat, modo automático entre OpenRouter y Ollama, recomendación de modelo local según el equipo y un puente opcional a Open Interpreter para tareas reales en el PC.

## Funciones

- **Automático por defecto:** si hay una clave de OpenRouter, intenta usar la nube; si falla, indica el cambio y prueba Ollama local. Sin clave, intenta Ollama.
- **Modelo local recomendado según hardware:** estima RAM y núcleos de CPU y recomienda `qwen2.5:0.5b`, `qwen2.5:1.5b` o `qwen2.5:3b`. No descarga modelos nuevos desde Ajustes sin que el usuario lo pida.
- **Guía de API en la aplicación:** enlace directo para crear la clave, instrucciones para guardarla y comprobación antes de usarla.
- **Agente de escritorio opcional:** el botón «Agente PC» abre una terminal con Open Interpreter y le pasa la tarea escrita en OpenChat.
- Historial local, guardado de archivos con confirmación antes de sobrescribir y configuración privada en el perfil del usuario.

## Instalar en Linux

Para instalar la aplicación de chat (sin descargar un modelo local):

```sh
curl -fsSL https://raw.githubusercontent.com/openchat-oc/OpenChat/main/install.sh | sh
```

Para instalar también Ollama y descargar el modelo recomendado para el equipo:

```sh
curl -fsSL https://raw.githubusercontent.com/openchat-oc/OpenChat/main/install.sh | env OPENCHAT_INSTALL_OLLAMA=1 sh
```

El instalador elige un tamaño conservador de modelo según la RAM y el número de núcleos. La descarga de Ollama es opcional porque puede ocupar varios GB y consumir memoria.

Para iniciar: `~/.local/bin/openchat`

Para desinstalar solo OpenChat: `~/.local/bin/openchat-uninstall`. Ollama y sus modelos no se eliminan.

## Instalar en Windows

Abre PowerShell y ejecuta:

```powershell
irm https://raw.githubusercontent.com/openchat-oc/OpenChat/main/install.ps1 | iex
```

Por defecto instala OpenChat sin descargar un modelo local. Para incluir Ollama, define `OPENCHAT_INSTALL_OLLAMA=1` antes de ejecutar el instalador. El modelo recomendado se elige a partir de la RAM y los núcleos de CPU.

Los accesos directos `OpenChat.cmd` y `Desinstalar OpenChat.cmd` se crean en el Escritorio.

## Crear y configurar una API de OpenRouter

1. Abre [OpenRouter — Keys](https://openrouter.ai/settings/keys) e inicia sesión.
2. Crea una clave nueva. Si el proveedor o el modelo tiene límites, revisa el saldo, los créditos y las condiciones mostradas por OpenRouter.
3. Copia la clave completa y pégala en OpenChat → Ajustes. No la publiques, no la compartas y no la añadas a GitHub.
4. Pulsa «Comprobar y guardar». OpenChat valida la clave antes de almacenarla.
5. Deja **Automático** para preferir la nube y usar Ollama como alternativa, o selecciona **Nube** o **Local** para fijar el proveedor.

La clave se guarda en `~/.config/openchat/openrouter.key` con permisos restringidos en Linux. Las peticiones en modo nube se envían a OpenRouter; las peticiones locales se hacen al servicio de Ollama en `127.0.0.1:11434`.

## Agente de PC con Open Interpreter

OpenChat no instala Open Interpreter automáticamente: es una dependencia opcional y puede tener requisitos propios. Si ya tienes un entorno compatible, el botón **⚡ Agente PC** puede usarlo. En Linux, OpenChat busca primero:

- `~/.local/share/open-interpreter-classic-env/bin/python`
- `~/.local/share/openchat-interpreter/bin/python`
- el intérprete de Python con el que se ejecuta OpenChat

Si no tienes uno, crea un entorno separado para evitar conflictos con las dependencias de OpenChat:

```sh
python3 -m venv ~/.local/share/openchat-interpreter
~/.local/share/openchat-interpreter/bin/pip install open-interpreter
```

Cierra y vuelve a abrir OpenChat si acabas de instalarlo. Escribe una tarea concreta en «Agente PC»; se abrirá una terminal con Open Interpreter. **Revisa cada acción y aprueba solo el código que entiendas.** El modo automático de ejecución se mantiene desactivado: el agente puede leer y modificar archivos o ejecutar comandos únicamente mediante las herramientas y aprobaciones que permita Open Interpreter. Haz una copia de seguridad antes de pedir cambios importantes.

## Ejecutar desde el código

```sh
python -m pip install -r requirements.txt
python -m app.main
```

Pruebas:

```sh
python -m unittest discover -s tests -v
```

Las pruebas actuales no sustituyen una comprobación manual de la interfaz ni pruebas reales con una clave de OpenRouter, Ollama y Open Interpreter.

## Licencia

MIT
