"""Creación y guardado seguro de archivos, y extracción de archivos generados por el modelo."""
from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

_WIN_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class UnsafePath(ValueError):
    pass


def sanitize_filename(name: str, fallback: str = "archivo.txt") -> str:
    """Devuelve solo un nombre de archivo (sin carpetas) y válido en Linux y Windows."""
    base = str(name).replace("\\", "/").split("/")[-1].strip().strip(".")
    base = _BAD_CHARS.sub("_", base).strip()
    if not base or base in (".", ".."):
        return fallback
    stem = base.split(".")[0].lower()
    if stem in _WIN_RESERVED:
        base = "_" + base
    return base[:150]


def safe_join(root: Path, relative: str) -> Path:
    """Resuelve ``relative`` dentro de ``root``; lanza UnsafePath si intenta salir (.., rutas absolutas, enlaces)."""
    root_r = Path(root).resolve()
    rel = str(relative).replace("\\", "/")
    if not rel or "\x00" in rel:
        raise UnsafePath("Ruta vacía o inválida.")
    if rel.startswith(("/", "~")) or re.match(r"^[A-Za-z]:", rel):
        raise UnsafePath("No se permiten rutas absolutas; usa una ruta dentro del espacio de trabajo.")
    target = (root_r / rel).resolve()
    try:
        target.relative_to(root_r)
    except ValueError:
        raise UnsafePath("La ruta sale del espacio de trabajo autorizado.") from None
    return target


def is_inside(root: Path, target: Path) -> bool:
    try:
        Path(target).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for i in range(2, 10_000):
        cand = path.with_name(f"{path.stem} ({i}){path.suffix}")
        if not cand.exists():
            return cand
    raise FileExistsError(str(path))


def save_text(path: Path, content: str, overwrite: bool = False) -> Path:
    """Escritura atómica con verificación posterior. Nunca sobrescribe sin ``overwrite=True``."""
    path = Path(path)
    if path.exists() and not overwrite:
        raise FileExistsError(f"Ya existe: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    data = content.replace("\r\n", "\n")
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".openchat-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    if path.read_text(encoding="utf-8") != data:
        raise OSError(f"La verificación del archivo guardado falló: {path}")
    return path


# ------------------------------------------------------------ bloques <openchat-file>
_FILE_RE = re.compile(r"""<openchat-file\s+name\s*=\s*(?P<q>["'])(?P<name>.*?)(?P=q)\s*>(?P<body>.*?)</openchat-file\s*>""",
                      re.S | re.I)
_OPEN_RE = re.compile(r"""<openchat-file\s+name\s*=\s*(["'])(.*?)\1\s*>""", re.I)
_FENCE_RE = re.compile(r"\A\s*```[\w+\-.]*\n(?P<code>.*?)\n?```\s*\Z", re.S)


@dataclass
class GeneratedFile:
    name: str
    content: str
    complete: bool = True


def normalize_content(body: str) -> str:
    text = body.replace("\r\n", "\n")
    text = text.lstrip("\n").rstrip()
    m = _FENCE_RE.match(text)
    if m:
        text = m.group("code")
    # Algunos modelos devuelven «\n» literales en lugar de saltos de línea reales.
    if "\n" not in text and text.count("\\n") >= 2:
        text = text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")
    return text + "\n"


def extract_files(text: str) -> list[GeneratedFile]:
    files: dict[str, GeneratedFile] = {}
    pos = 0
    for m in _FILE_RE.finditer(text):
        name = sanitize_filename(m.group("name"))
        files[name] = GeneratedFile(name, normalize_content(m.group("body")))
        pos = m.end()
    tail = _OPEN_RE.search(text, pos)  # bloque abierto y nunca cerrado: respuesta cortada
    if tail:
        name = sanitize_filename(tail.group(2))
        files[name] = GeneratedFile(name, normalize_content(text[tail.end():]), complete=False)
    return list(files.values())


def strip_file_blocks(text: str) -> str:
    def repl(m: re.Match) -> str:
        return f"📄 Archivo preparado: {sanitize_filename(m.group('name'))}"
    out = _FILE_RE.sub(repl, text)
    tail = _OPEN_RE.search(out)
    if tail:
        out = out[:tail.start()] + f"📄 Archivo incompleto: {sanitize_filename(tail.group(2))} (la respuesta se cortó)"
    return out
