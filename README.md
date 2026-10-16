# OpenChat

Asistente de chat de escritorio para Linux y Windows, con interfaz PySide6. Usa Laguna a través de OpenRouter y prueba Ollama local si la petición en la nube falla.

## Funciones
- Interfaz de chat de escritorio.
- Configuración de clave OpenRouter desde la app.
- Clave guardada fuera del repositorio en ~/.config/openchat/openrouter.key.
- Modelo en la nube: poolside/laguna-s-2.1:free.
- Respaldo local opcional: Ollama con qwen2.5:1.5b.
- Instaladores para Linux y Windows; no necesita Releases.

## Linux
Ejecuta en una terminal:

    curl -fsSL https://raw.githubusercontent.com/openchat-oc/OpenChat/main/install.sh | sh

El instalador usa gestores comunes (pacman, apt, dnf, zypper), instala dependencias del sistema si faltan, crea ~/OpenChat y añade OpenChat al menú de aplicaciones.

## Windows
En PowerShell:

    irm https://raw.githubusercontent.com/openchat-oc/OpenChat/main/install.ps1 | iex

Se necesitan Python 3 y Git. El instalador indica dónde conseguirlos si faltan.

## Primera ejecución
Crea una clave en https://openrouter.ai/settings/keys y pégala en el diálogo de configuración de OpenChat. Para respaldo local instala Ollama desde https://ollama.com y ejecuta:

    ollama pull qwen2.5:1.5b

## Ejecutar desde el código

    python -m pip install -r requirements.txt
    python -m app.main

## Privacidad
No publiques tu clave API ni la guardes en el repositorio. Cuando usa OpenRouter, los mensajes se envían a ese servicio; el modo Ollama envía peticiones a localhost.

## Licencia
MIT
