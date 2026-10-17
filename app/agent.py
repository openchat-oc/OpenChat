"""Open Interpreter bridge for opt-in, user-approved desktop tasks."""
from __future__ import annotations

import base64
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


def _python_with_interpreter() -> str | None:
    """Find a Python environment that has Open Interpreter installed."""
    candidates = [
        Path.home() / ".local/share/open-interpreter-classic-env/bin/python",
        Path.home() / ".local/share/openchat-interpreter/bin/python",
        Path.home() / ".local/share/open-interpreter-classic-env/Scripts/python.exe",
        Path.home() / ".local/share/openchat-interpreter/Scripts/python.exe",
        Path(sys.executable),
    ]
    for candidate in candidates:
        if candidate.exists():
            try:
                check = subprocess.run(
                    [str(candidate), "-c", "import interpreter"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                    check=False,
                )
                if check.returncode == 0:
                    return str(candidate)
            except (OSError, subprocess.TimeoutExpired):
                continue
    return None


def launch_agent(task: str) -> None:
    """Open a terminal running Open Interpreter for the requested task.

    Open Interpreter's normal approval mode is deliberately retained: this
    function never enables auto-run and never invokes the task as a shell command.
    """
    task = task.strip()
    if not task:
        raise ValueError("Escribe qué quieres que haga el agente.")
    python = _python_with_interpreter()
    if not python:
        raise FileNotFoundError(
            "No encuentro Open Interpreter. Instálalo en un entorno separado y "
            "vuelve a intentarlo. En Linux: python -m venv "
            "~/.local/share/openchat-interpreter && "
            "~/.local/share/openchat-interpreter/bin/pip install open-interpreter"
        )

    encoded = base64.b64encode(task.encode("utf-8")).decode("ascii")
    code = (
        "import base64; from interpreter import interpreter; "
        "interpreter.auto_run_mode='off'; "
        f"interpreter.chat(base64.b64decode('{encoded}').decode('utf-8')); "
        "input('Tarea terminada. Pulsa Intro para cerrar esta ventana...')"
    )

    if sys.platform.startswith("linux"):
        terminals = [
            ("konsole", ["konsole", "-e"]),
            ("kgx", ["kgx", "--"]),
            ("gnome-terminal", ["gnome-terminal", "--"]),
            ("xfce4-terminal", ["xfce4-terminal", "--execute"]),
            ("x-terminal-emulator", ["x-terminal-emulator", "-e"]),
        ]
        for name, prefix in terminals:
            if shutil.which(name):
                shell_line = " ".join(shlex.quote(part) for part in [python, "-c", code])
                subprocess.Popen(prefix + ["bash", "-lc", shell_line])
                return
        raise RuntimeError(
            "No encuentro un emulador de terminal compatible. Abre una terminal "
            f"y ejecuta: {shlex.quote(python)} -c {shlex.quote(code)}"
        )

    if sys.platform == "win32":
        command = f"& '{python.replace(chr(39), chr(39)+chr(34)+chr(39)+chr(34)+chr(39))}' -c "
        command += "'" + code.replace("'", "''") + "'; Read-Host 'Pulsa Intro para cerrar'"
        subprocess.Popen(
            ["powershell.exe", "-NoExit", "-Command", command],
            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
        )
        return

    raise RuntimeError("El agente de escritorio está preparado para Linux y Windows.")
