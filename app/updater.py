"""Comprobación de versiones. Distingue «actualizado», «hay actualización» y «no se pudo comprobar»."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

from . import __version__

VERSION_URL = "https://raw.githubusercontent.com/openchat-oc/OpenChat/main/VERSION"
UP_TO_DATE, AVAILABLE, ERROR = "up_to_date", "available", "error"


@dataclass
class UpdateResult:
    state: str
    installed: str
    latest: str = ""
    message: str = ""


def parse_version(text: str) -> tuple[int, ...] | None:
    m = re.match(r"^\s*v?(\d+(?:\.\d+){0,3})\s*$", text or "")
    return tuple(int(p) for p in m.group(1).split(".")) if m else None


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _git(root: Path, *args: str, timeout: int = 10) -> str:
    out = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                         timeout=timeout, check=True)
    return out.stdout.strip()


def default_fetch(url: str) -> str:
    r = requests.get(url, timeout=(5, 10), headers={"Cache-Control": "no-cache"})
    r.raise_for_status()
    return r.text


def check_for_update(fetch: Callable[[str], str] = default_fetch, installed: str = __version__,
                     root: Path | None = None) -> UpdateResult:
    """Compara con el archivo VERSION de ``main``. Si no existe aún, compara commits con git."""
    root = root or repo_root()
    inst = parse_version(installed)
    try:
        remote_text = fetch(VERSION_URL)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return _check_by_commit(root, installed)
        return UpdateResult(ERROR, installed, message=f"No se pudo consultar GitHub ({exc}).")
    except requests.RequestException:
        return UpdateResult(ERROR, installed, message="No se pudo comprobar: sin conexión con GitHub.")
    latest = parse_version(remote_text)
    if latest is None or inst is None:
        return UpdateResult(ERROR, installed, message="El archivo VERSION remoto no tiene un formato válido.")
    if latest > inst:
        return UpdateResult(AVAILABLE, installed, ".".join(map(str, latest)),
                            f"Hay una versión nueva: {'.'.join(map(str, latest))} (tienes {installed}).")
    return UpdateResult(UP_TO_DATE, installed, ".".join(map(str, latest)), "OpenChat está actualizado.")


def _check_by_commit(root: Path, installed: str) -> UpdateResult:
    try:
        if not (root / ".git").exists():
            return UpdateResult(ERROR, installed, message="Esta copia no es un clon de Git; no puedo comprobar actualizaciones.")
        remote = _git(root, "ls-remote", "origin", "refs/heads/main", timeout=15).split()
        if not remote:
            return UpdateResult(ERROR, installed, message="GitHub no devolvió la versión de main.")
        local = _git(root, "rev-parse", "HEAD")
        if remote[0] == local:
            return UpdateResult(UP_TO_DATE, installed, message="OpenChat está actualizado.")
        try:
            _git(root, "merge-base", "--is-ancestor", remote[0], "HEAD")
            return UpdateResult(UP_TO_DATE, installed, message="Tu copia está por delante de main.")
        except subprocess.CalledProcessError:
            return UpdateResult(AVAILABLE, installed, message="Hay cambios nuevos en main.")
    except (subprocess.SubprocessError, OSError) as exc:
        return UpdateResult(ERROR, installed, message=f"No se pudo comprobar con Git: {exc}")


def apply_update(root: Path | None = None) -> tuple[bool, str]:
    """``git pull --ff-only`` (no pierde datos: configuración e historial viven fuera del repo)."""
    root = root or repo_root()
    if not (root / ".git").exists():
        return False, "Esta copia no es un clon de Git. Reinstala con el instalador."
    try:
        if _git(root, "status", "--porcelain"):
            return False, "Hay cambios locales sin guardar en la carpeta de OpenChat; no actualizo para no perderlos."
        out = _git(root, "pull", "--ff-only", timeout=120)
        req = root / "requirements.txt"
        if req.exists():
            import sys
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(req)],
                           capture_output=True, text=True, timeout=600, check=True)
        return True, out or "Actualizado. Reinicia OpenChat."
    except subprocess.CalledProcessError as exc:
        return False, (exc.stderr or exc.stdout or str(exc)).strip()[:400]
    except (subprocess.SubprocessError, OSError) as exc:
        return False, str(exc)
