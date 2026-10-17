# OpenChat

![Logo de OpenChat](app/logo.svg)

**OpenChat** es un asistente de IA de escritorio para Linux y Windows. Conversa, explica, programa, crea y edita archivos y, si lo activas, trabaja sobre un proyecto con herramientas y **con tu permiso**. Puedes usar modelos en la **nube (OpenRouter)** o **locales (Ollama)**. OpenChat nunca cambia de proveedor en silencio.

**Chispa** es la mascota de OpenChat (la ves en la configuración, en los estados vacíos y mientras «OpenChat está pensando»). Chispa **no** es la IA ni el nombre del asistente.

## Instalación

**Linux (CachyOS/Arch, Debian/Ubuntu, Fedora, openSUSE):**

    curl -fsSL https://raw.githubusercontent.com/openchat-oc/OpenChat/main/install.sh | sh

**Windows 10/11 (PowerShell):**

    irm https://raw.githubusercontent.com/openchat-oc/OpenChat/main/install.ps1 | iex

Los instaladores comprueban lo que ya tienes e instalan solo lo que falta (Python 3.9+, Git, bibliotecas de Qt), crean un entorno virtual aislado, comprueban que Qt arranca, y pueden ejecutarse de nuevo sin perder tu configuración. Piden permisos de administrador únicamente para instalar paquetes del sistema y te dicen por qué.

**IA local (opcional).** Por defecto **no** se instala Ollama ni se descarga ningún modelo. Para incluirlos:

    curl -fsSL https://raw.githubusercontent.com/openchat-oc/OpenChat/main/install.sh | env OPENCHAT_INSTALL_OLLAMA=1 sh

(En Windows: `$env:OPENCHAT_INSTALL_OLLAMA = "1"` antes del comando.) Modelo local por defecto: `qwen2.5:1.5b` (≈1 GB o más); cámbialo con `OPENCHAT_MODEL`. En Arch/CachyOS, Ollama se instala con `pacman`; en otras distribuciones se usa el instalador oficial de Ollama (script remoto que **no** puedo auditar por ti).

Variables útiles: `OPENCHAT_ASSUME_YES=1` (sin preguntas), `OPENCHAT_BRANCH`, `OPENCHAT_REPO`.

**Desinstalar:** `openchat-uninstall` (Linux) o el acceso «Desinstalar OpenChat» del escritorio (Windows). Elimina la aplicación y conserva Ollama, sus modelos y los paquetes del sistema. Pregunta **por separado** si quieres borrar la clave/configuración y el historial.

**Desde el código:**

    python -m venv .venv && . .venv/bin/activate    # Windows: .venv\Scripts\activate
    python -m pip install -r requirements.txt
    python -m app.main

## Primer arranque

Un asistente guiado (con Chispa) te lleva paso a paso: **nube** (OpenRouter) o **local** (Ollama).

- **Nube:** pega tu clave de OpenRouter (con botón para mostrar/ocultar), pulsa *Comprobar conexión* —se hace una consulta real, no solo se valida el formato— y elige modelo (la lista se carga en vivo desde OpenRouter). No avanza hasta que la comprobación funcione.
- **Local:** detecta Ollama y los modelos instalados, explica cómo instalarlo si falta y puede descargar un modelo con barra de progreso y botón de cancelar. Instalar Ollama no basta: hace falta un modelo descargado.

Puedes cambiar de motor y de modelo en la barra lateral y repetir el asistente desde *Ajustes*. Si falta la clave o desaparece el modelo, OpenChat te lo explica y te ofrece configurarlo; no se bloquea.

## Qué hace

- **Chat** con streaming, botón *Detener* (o `Esc`), historial persistente (renombrar, eliminar, continuar), bloques de código copiables y enlaces seguros. El texto que escribes no se pierde si hay un error. `Intro` envía, `Mayús+Intro` salta de línea, y puedes empezar a escribir sin hacer clic en la caja.
- **Archivos:** si pides un archivo, OpenChat lo prepara en un panel (vista previa y edición), lo guarda donde elijas, **verifica lo escrito**, no sobrescribe sin preguntar y nunca ejecuta lo generado.
- **Modo agente** (desactivado por defecto): el modelo propone herramientas (leer/buscar/editar/crear archivos, ejecutar pruebas y comandos) y OpenChat valida, comprueba permisos, ejecuta y devuelve el resultado real. Ver *Permisos*.
- **Actualizaciones:** comprueba el archivo `VERSION` de `main` en GitHub (o, si no existe, compara commits con `git`). Distingue «actualizado», «hay actualización» y «no se pudo comprobar». Actualizar ejecuta `git pull --ff-only` solo con el árbol limpio; tu configuración e historial no se tocan.

## Permisos del modo agente

| Acción | Comportamiento |
|---|---|
| Leer, listar, buscar dentro del espacio de trabajo | Automático. Archivos sensibles (`.env`, `*.pem`, `id_rsa`…) piden confirmación porque su contenido se enviaría al modelo |
| Crear/editar archivos | Pregunta (o automático si eliges «permitir ediciones» en Ajustes) |
| Borrar archivos | Siempre pregunta |
| Ejecutar comandos | Sin shell, con tiempo límite y entorno sin claves. Pruebas/`git status` pueden ser automáticos; el resto pregunta |
| Instalar software (`pip`, `npm`, `pacman`, `winget`…) | Siempre pregunta |
| `sudo`, `rm`, `dd`, shells, rutas fuera del espacio de trabajo | **Bloqueado** |

Límites: 12 pasos, 15 minutos, detección de bucles, cancelable en cualquier momento. El contenido de archivos y los resultados de herramientas se tratan como **datos**, no como instrucciones.

## Privacidad

- **Nube:** tus mensajes (y, en modo agente, el contenido de los archivos que el agente lea) se envían a OpenRouter y al modelo elegido. **Local:** todo se queda en tu equipo (`127.0.0.1:11434`).
- Datos personales en `~/.config/openchat` (configuración, historial SQLite, registro), fuera del repositorio. La **clave de OpenRouter** se guarda en el llavero del sistema si existe; si no, en un archivo con permisos `600` (en Windows los permisos POSIX no se aplican: se protege con la cuenta de usuario). Los registros y errores ocultan las claves.
- Nada se sube a GitHub automáticamente. No hay telemetría. La única consulta de red propia es la comprobación de actualizaciones (se desactiva en Ajustes).

## Pruebas

    python -m pip install -r requirements-dev.txt
    python -m pytest -q

Cubren: configuración y secretos, historial y migración desde la versión anterior, rutas y guardado de archivos, proveedores contra servidores HTTP locales que imitan OpenRouter (SSE) y Ollama, el agente y su política de permisos, el actualizador (incluido `git` real), el asistente de configuración y la ventana principal con Qt *offscreen* (teclado, streaming, cancelar, errores, archivos).

## Limitaciones conocidas

- El llavero del sistema solo se probó con un llavero simulado (en este entorno no hay uno real); la ruta del archivo privado sí se probó de verdad.
- **No se ha probado** contra OpenRouter real ni con un modelo de Ollama real (se usan servidores simulados); depende de que esos servicios mantengan su API.
- Instalador de **Windows**: su sintaxis está validada, pero no se ha ejecutado en Windows. Instalador de **Linux**: ejecutado de verdad en Ubuntu; la detección de CachyOS/Arch se probó con un `pacman` simulado y los nombres de paquetes de Arch/Fedora/openSUSE no se han verificado en esas distribuciones.
- La interfaz se ha probado en modo *offscreen*; falta revisarla a mano en Wayland/KDE y en Windows (foco, diálogos del sistema, escalado).
- La IA no «recuerda» entre conversaciones: solo ve la conversación abierta, recortada a ~24 000 caracteres (OpenChat te avisa cuando recorta). No hay resúmenes automáticos.
- El agente usa un protocolo de herramientas en texto, así que depende de que el modelo lo respete; los modelos pequeños pueden fallar.
- La actualización no verifica firmas: confía en `git` sobre HTTPS desde el repositorio. No hay instaladores firmados.
- Respaldo automático a Ollama: existe pero está **desactivado por defecto** y avisa en el chat cuando se usa.

## Licencia

MIT
