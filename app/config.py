"""Configuración, credenciales y registro de errores de OpenChat.

Los datos personales viven en ``~/.config/openchat`` (o en ``$OPENCHAT_HOME``), fuera del
repositorio, de modo que actualizar OpenChat nunca los toca.
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
import re
from pathlib import Path
from typing import Any

SERVICE = "openchat"
KEY_USER = "openrouter"
DEFAULT_CLOUD_MODEL = "poolside/laguna-s-2.1:free"
DEFAULT_LOCAL_MODEL = "qwen2.5:1.5b"

DEFAULTS: dict[str, Any] = {
    "setup_done": False,
    "mode": "cloud",                 # "cloud" (OpenRouter) | "local" (Ollama)
    "cloud_model": DEFAULT_CLOUD_MODEL,
    "local_model": DEFAULT_LOCAL_MODEL,
    "fallback_to_local": False,      # respaldo automático a Ollama: explícito y visible
    "auto_update_check": True,
    "agent_enabled": False,
    "agent_permission": "ask",       # "ask" | "auto_edits"
    "workspace": "",
    "temperature": 0.6,
}


def config_dir() -> Path:
    env = os.environ.get("OPENCHAT_HOME")
    return Path(env) if env else Path.home() / ".config" / "openchat"


def default_workspace() -> Path:
    return Path.home() / "OpenChat-Workspace"


# ------------------------------------------------------------------ redacción de secretos
_SECRET_PATTERNS = [
    re.compile(r"sk-or-[A-Za-z0-9_\-]{6,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{6,}"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9_\-\.]{12,}"),
]


def redact(text: object, extra: tuple[str, ...] = ()) -> str:
    out = str(text)
    for secret in extra:
        if secret and len(secret) >= 8:
            out = out.replace(secret, "[clave oculta]")
    for pat in _SECRET_PATTERNS:
        out = pat.sub(lambda m: (m.group(1) if m.lastindex else "") + "[clave oculta]", out)
    return out


class _RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact(record.getMessage())
            record.args = ()
        except Exception:  # pragma: no cover - nunca romper el log
            pass
        return True


def setup_logging() -> logging.Logger:
    log = logging.getLogger("openchat")
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    log.propagate = False
    try:
        config_dir().mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = logging.handlers.RotatingFileHandler(
            config_dir() / "openchat.log", maxBytes=512_000, backupCount=2, encoding="utf-8")
    except OSError:
        handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(_RedactFilter())
    log.addHandler(handler)
    return log


# ------------------------------------------------------------------ ajustes
class Settings:
    def __init__(self, path: Path | None = None):
        self.path = path or (config_dir() / "settings.json")
        self.data: dict[str, Any] = dict(DEFAULTS)
        self.loaded_from_disk = False
        self.load()

    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self.data.update({k: v for k, v in raw.items() if k in DEFAULTS})
                self.loaded_from_disk = True
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            try:  # archivo corrupto: se conserva una copia y se parte de los valores por defecto
                self.path.replace(self.path.with_suffix(".json.bak"))
            except OSError:
                pass

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            tmp.chmod(0o600)
        except OSError:
            pass
        tmp.replace(self.path)

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        if key not in DEFAULTS:
            raise KeyError(key)
        self.data[key] = value

    def update(self, **kw: Any) -> None:
        for k, v in kw.items():
            self[k] = v
        self.save()

    def workspace_path(self) -> Path:
        return Path(self.data["workspace"]) if self.data["workspace"] else default_workspace()


# ------------------------------------------------------------------ credenciales
def _keyring():
    """Devuelve el módulo keyring solo si hay un backend real del sistema."""
    try:
        import keyring
        backend = keyring.get_keyring()
        if getattr(backend, "priority", 0) <= 0:
            return None
        return keyring
    except Exception:
        return None


def _key_file() -> Path:
    return config_dir() / "openrouter.key"


def _legacy_key_file() -> Path:
    return Path.home() / ".config" / "oi-auto" / "openrouter.key"


def get_api_key() -> str:
    kr = _keyring()
    if kr:
        try:
            value = kr.get_password(SERVICE, KEY_USER)
            if value:
                return value.strip()
        except Exception:
            pass
    for path in (_key_file(), _legacy_key_file()):
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value:
            if path != _key_file():
                set_api_key(value)  # migración desde la ubicación antigua
            return value
    return ""


def set_api_key(key: str) -> str:
    """Guarda la clave. Devuelve ``"keyring"`` o ``"file"`` según dónde quedó."""
    key = key.strip()
    kr = _keyring()
    if kr:
        try:
            kr.set_password(SERVICE, KEY_USER, key)
            try:
                _key_file().unlink()
            except FileNotFoundError:
                pass
            return "keyring"
        except Exception:
            pass
    config_dir().mkdir(parents=True, exist_ok=True)
    fd = os.open(_key_file(), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(key)
    try:
        _key_file().chmod(0o600)
    except OSError:
        pass
    return "file"


def delete_api_key() -> None:
    kr = _keyring()
    if kr:
        try:
            kr.delete_password(SERVICE, KEY_USER)
        except Exception:
            pass
    for path in (_key_file(), _legacy_key_file()):
        try:
            path.unlink()
        except OSError:
            pass


def key_format_warning(key: str) -> str:
    key = key.strip()
    if not key:
        return "Introduce una clave."
    if any(c.isspace() for c in key):
        return "La clave no puede contener espacios ni saltos de línea."
    if not key.startswith("sk-or-"):
        return "No parece una clave de OpenRouter (suelen empezar por sk-or-)."
    if len(key) < 20:
        return "La clave parece incompleta."
    return ""


def mask_key(key: str) -> str:
    return "sk-or-…" + key[-4:] if len(key) > 10 else "••••"
