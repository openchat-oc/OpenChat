"""Herramientas del agente: argumentos tipados, validación y resultados estructurados."""
from __future__ import annotations

import os
import platform
import shlex
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .. import __version__
from ..fileops import UnsafePath, safe_join, save_text
from ..providers.base import CancelToken, Cancelled

MAX_OUTPUT = 6000
MAX_READ_BYTES = 100_000
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache", ".pytest_cache", "dist", "build"}


class ToolError(Exception):
    pass


@dataclass
class ToolResult:
    ok: bool
    output: str
    summary: str = ""


@dataclass
class ToolContext:
    workspace: Path
    cancel: CancelToken = field(default_factory=CancelToken)
    command_timeout: int = 120


@dataclass
class ToolSpec:
    name: str
    description: str
    params: dict[str, tuple[type, bool, str]]   # nombre -> (tipo, obligatorio, ayuda)
    risk: str                                   # read | write | exec | destructive
    fn: Callable[..., ToolResult]


def clip(text: str, limit: int = MAX_OUTPUT) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return text[:half] + f"\n… [{len(text) - limit} caracteres omitidos] …\n" + text[-half:]


def validate_args(spec: ToolSpec, args: Any) -> dict[str, Any]:
    if not isinstance(args, dict):
        raise ToolError("Los argumentos deben ser un objeto JSON.")
    unknown = set(args) - set(spec.params)
    if unknown:
        raise ToolError("Argumentos desconocidos: " + ", ".join(sorted(unknown)))
    clean: dict[str, Any] = {}
    for key, (typ, required, _doc) in spec.params.items():
        if key not in args:
            if required:
                raise ToolError(f"Falta el argumento obligatorio «{key}».")
            continue
        val = args[key]
        if typ is bool and not isinstance(val, bool):
            raise ToolError(f"«{key}» debe ser verdadero o falso.")
        if typ is int and (isinstance(val, bool) or not isinstance(val, int)):
            raise ToolError(f"«{key}» debe ser un número entero.")
        if typ is str and not isinstance(val, str):
            raise ToolError(f"«{key}» debe ser texto.")
        if typ is list and not (isinstance(val, list) and all(isinstance(x, str) for x in val)):
            raise ToolError(f"«{key}» debe ser una lista de textos.")
        clean[key] = val
    return clean


# ------------------------------------------------------------------ implementaciones
def _path(ctx: ToolContext, rel: str) -> Path:
    try:
        return safe_join(ctx.workspace, rel or ".")
    except UnsafePath as exc:
        raise ToolError(str(exc)) from exc


def t_list_dir(ctx: ToolContext, path: str = ".") -> ToolResult:
    p = _path(ctx, path)
    if not p.is_dir():
        raise ToolError(f"No es una carpeta: {path}")
    rows = []
    for child in sorted(p.iterdir(), key=lambda c: (not c.is_dir(), c.name.lower()))[:200]:
        rows.append(("📁 " if child.is_dir() else "   ") + child.name + ("/" if child.is_dir() else ""))
    return ToolResult(True, "\n".join(rows) or "(carpeta vacía)", f"{len(rows)} elementos en {path}")


def t_read_file(ctx: ToolContext, path: str) -> ToolResult:
    p = _path(ctx, path)
    if not p.is_file():
        raise ToolError(f"No existe el archivo: {path}")
    raw = p.read_bytes()[:MAX_READ_BYTES + 1]
    if b"\x00" in raw[:4096]:
        raise ToolError("Es un archivo binario; no se puede leer como texto.")
    text = raw[:MAX_READ_BYTES].decode("utf-8", "replace")
    note = "\n[… archivo truncado a 100 KB]" if len(raw) > MAX_READ_BYTES else ""
    return ToolResult(True, text + note, f"Leído {path} ({len(text)} caracteres)")


def t_search_text(ctx: ToolContext, query: str, path: str = ".") -> ToolResult:
    if not query:
        raise ToolError("La búsqueda está vacía.")
    base = _path(ctx, path)
    hits: list[str] = []
    needle = query.lower()
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            fp = Path(dirpath) / fn
            try:
                if fp.stat().st_size > 1_000_000:
                    continue
                with fp.open("r", encoding="utf-8") as fh:
                    for no, line in enumerate(fh, 1):
                        if needle in line.lower():
                            hits.append(f"{fp.relative_to(ctx.workspace.resolve())}:{no}: {line.strip()[:160]}")
                            if len(hits) >= 50:
                                return ToolResult(True, "\n".join(hits) + "\n[… más resultados omitidos]", "50+ coincidencias")
            except (OSError, UnicodeDecodeError):
                continue
    return ToolResult(True, "\n".join(hits) or "Sin coincidencias.", f"{len(hits)} coincidencias")


def t_file_info(ctx: ToolContext, path: str) -> ToolResult:
    p = _path(ctx, path)
    if not p.exists():
        raise ToolError(f"No existe: {path}")
    st = p.stat()
    kind = "carpeta" if p.is_dir() else "archivo"
    return ToolResult(True, f"{kind}; {st.st_size} bytes; modificado {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.st_mtime))}", f"Metadatos de {path}")


def t_write_file(ctx: ToolContext, path: str, content: str, overwrite: bool = False) -> ToolResult:
    p = _path(ctx, path)
    if p.is_dir():
        raise ToolError("La ruta es una carpeta.")
    try:
        save_text(p, content, overwrite=overwrite)
    except FileExistsError:
        raise ToolError(f"{path} ya existe. Usa edit_file para modificarlo o overwrite=true para reemplazarlo.") from None
    except OSError as exc:
        raise ToolError(f"No se pudo guardar: {exc}") from exc
    return ToolResult(True, f"Guardado y verificado: {path} ({len(content)} caracteres)", f"Escrito {path}")


def t_edit_file(ctx: ToolContext, path: str, old: str, new: str) -> ToolResult:
    p = _path(ctx, path)
    if not p.is_file():
        raise ToolError(f"No existe el archivo: {path}")
    if not old:
        raise ToolError("«old» no puede estar vacío.")
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count == 0:
        raise ToolError("El texto a reemplazar no aparece en el archivo (revisa espacios y saltos de línea).")
    if count > 1:
        raise ToolError(f"El texto aparece {count} veces; incluye más contexto para que sea único.")
    save_text(p, text.replace(old, new, 1), overwrite=True)
    return ToolResult(True, f"Editado {path}: 1 reemplazo", f"Editado {path}")


def t_make_dir(ctx: ToolContext, path: str) -> ToolResult:
    p = _path(ctx, path)
    p.mkdir(parents=True, exist_ok=True)
    return ToolResult(True, f"Carpeta lista: {path}", f"Carpeta {path}")


def t_delete_file(ctx: ToolContext, path: str) -> ToolResult:
    p = _path(ctx, path)
    if p.is_dir():
        raise ToolError("Solo se pueden borrar archivos, no carpetas.")
    if not p.exists():
        raise ToolError(f"No existe: {path}")
    p.unlink()
    return ToolResult(True, f"Eliminado: {path}", f"Eliminado {path}")


def t_env_info(ctx: ToolContext) -> ToolResult:
    return ToolResult(True, f"OpenChat {__version__}\nSistema: {platform.system()} {platform.release()}\n"
                      f"Python: {platform.python_version()}\nEspacio de trabajo: {ctx.workspace}\n"
                      f"git: {'sí' if shutil.which('git') else 'no'}", "Información del entorno")


def _resolve_argv(argv: list[str]) -> list[str]:
    argv = list(argv)
    if argv and Path(argv[0]).name.lower() in ("python", "python3", "py", "py.exe", "python.exe") and not shutil.which(argv[0]):
        argv[0] = sys.executable
    return argv


def _clean_env() -> dict[str, str]:
    drop = ("OPENROUTER", "ANTHROPIC", "OPENAI", "API_KEY", "SECRET", "TOKEN", "PASSWORD")
    return {k: v for k, v in os.environ.items() if not any(d in k.upper() for d in drop)}


def parse_command(command: Any) -> list[str]:
    if isinstance(command, list):
        argv = [str(c) for c in command]
    elif isinstance(command, str):
        try:
            argv = shlex.split(command, posix=(os.name != "nt"))
        except ValueError as exc:
            raise ToolError(f"Comando mal formado: {exc}") from exc
    else:
        raise ToolError("«command» debe ser una lista de argumentos.")
    if not argv:
        raise ToolError("Comando vacío.")
    return argv


def t_run_command(ctx: ToolContext, command: list[str], timeout: int = 0) -> ToolResult:
    argv = _resolve_argv(parse_command(command))
    limit = max(1, min(timeout or ctx.command_timeout, 300))
    try:
        proc = subprocess.Popen(argv, cwd=ctx.workspace, env=_clean_env(), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, errors="replace",
                                start_new_session=(os.name != "nt"))
    except FileNotFoundError:
        raise ToolError(f"No se encontró el programa «{argv[0]}».") from None
    except OSError as exc:
        raise ToolError(f"No se pudo ejecutar: {exc}") from exc

    def kill() -> None:
        try:
            if os.name == "nt":
                proc.kill()
            else:
                os.killpg(proc.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass

    start = time.monotonic()
    out = ""
    while True:
        try:
            out, _ = proc.communicate(timeout=0.25)
            break
        except subprocess.TimeoutExpired:
            if ctx.cancel.is_set():
                kill(); proc.communicate()
                raise Cancelled()
            if time.monotonic() - start > limit:
                kill()
                out, _ = proc.communicate()
                return ToolResult(False, clip(out) + f"\n[tiempo límite de {limit}s superado; proceso detenido]", "Tiempo agotado")
    ok = proc.returncode == 0
    return ToolResult(ok, clip(out) + f"\n[código de salida: {proc.returncode}]", f"{' '.join(argv[:4])} → {'OK' if ok else 'falló'} ({proc.returncode})")


def t_run_tests(ctx: ToolContext, args: list[str] | None = None) -> ToolResult:
    extra = args or []
    has_pytest = subprocess.run([sys.executable, "-m", "pytest", "--version"], capture_output=True, cwd=ctx.workspace).returncode == 0
    cmd = [sys.executable, "-m", "pytest", "-q", *extra] if has_pytest else [sys.executable, "-m", "unittest", "discover", *extra]
    return t_run_command(ctx, cmd)


def build_registry() -> dict[str, ToolSpec]:
    S = str
    specs = [
        ToolSpec("list_dir", "Lista el contenido de una carpeta.", {"path": (S, False, "carpeta relativa, por defecto «.»")}, "read", t_list_dir),
        ToolSpec("read_file", "Lee un archivo de texto.", {"path": (S, True, "ruta relativa")}, "read", t_read_file),
        ToolSpec("search_text", "Busca texto en los archivos del proyecto.", {"query": (S, True, "texto"), "path": (S, False, "carpeta")}, "read", t_search_text),
        ToolSpec("file_info", "Tamaño y fecha de un archivo o carpeta.", {"path": (S, True, "ruta")}, "read", t_file_info),
        ToolSpec("env_info", "Información del entorno y del espacio de trabajo.", {}, "read", t_env_info),
        ToolSpec("write_file", "Crea un archivo (o lo reemplaza con overwrite=true).", {"path": (S, True, "ruta"), "content": (S, True, "contenido completo"), "overwrite": (bool, False, "reemplazar si existe")}, "write", t_write_file),
        ToolSpec("edit_file", "Reemplaza un fragmento único de un archivo.", {"path": (S, True, "ruta"), "old": (S, True, "texto exacto actual"), "new": (S, True, "texto nuevo")}, "write", t_edit_file),
        ToolSpec("make_dir", "Crea una carpeta.", {"path": (S, True, "ruta")}, "write", t_make_dir),
        ToolSpec("delete_file", "Elimina un archivo (siempre pide confirmación).", {"path": (S, True, "ruta")}, "destructive", t_delete_file),
        ToolSpec("run_command", "Ejecuta un programa SIN shell. Pasa una lista de argumentos.", {"command": (list, True, "p. ej. [\"python\",\"-m\",\"pytest\",\"-q\"]"), "timeout": (int, False, "segundos (máx. 300)")}, "exec", t_run_command),
        ToolSpec("run_tests", "Ejecuta las pruebas del proyecto (pytest o unittest).", {"args": (list, False, "argumentos extra")}, "exec", t_run_tests),
    ]
    return {s.name: s for s in specs}


def describe_tools(registry: dict[str, ToolSpec]) -> str:
    lines = []
    for s in registry.values():
        params = ", ".join(f"{k}{'' if req else '?'}: {t.__name__}" for k, (t, req, _d) in s.params.items())
        lines.append(f"- {s.name}({params}) — {s.description}")
    return "\n".join(lines)
