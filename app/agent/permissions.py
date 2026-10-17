"""Política de permisos del agente. El modelo propone; esta capa decide."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..fileops import UnsafePath, safe_join
from .tools import ToolError, ToolSpec, parse_command

ALLOW, ASK, DENY = "allow", "ask", "deny"

SENSITIVE_NAME = re.compile(r"(^\.env($|\.)|\.pem$|\.key$|id_rsa|id_ed25519|credentials|secrets?\.|\.kdbx$|openrouter\.key)", re.I)
NEVER = {"sudo", "su", "doas", "pkexec", "dd", "shutdown", "reboot", "poweroff", "halt", "format", "diskpart",
         "rm", "rmdir", "del", "rd", "erase", "mkfs", "fdisk", "parted"}
SHELLS = {"sh", "bash", "zsh", "fish", "dash", "ksh", "csh", "cmd", "powershell", "pwsh"}
INSTALLERS = {"pip", "pip3", "npm", "pnpm", "yarn", "apt", "apt-get", "pacman", "yay", "dnf", "zypper", "brew", "winget", "choco", "cargo", "gem"}
SAFE_PREFIXES = [["pytest"], ["python", "-m", "pytest"], ["python", "-m", "unittest"], ["python", "-m", "compileall"],
                 ["python", "-m", "py_compile"], ["python", "-m", "ruff", "check"], ["ruff", "check"], ["flake8"],
                 ["git", "status"], ["git", "diff"], ["git", "log"]]


@dataclass
class Decision:
    action: str            # allow | ask | deny
    reason: str
    key: str = ""          # clave para «permitir durante esta tarea»
    detail: str = ""       # qué se va a hacer, para mostrar al usuario


def _norm(argv: list[str]) -> list[str]:
    out = list(argv)
    if out:
        name = Path(out[0]).name.lower().removesuffix(".exe")
        out[0] = "python" if re.fullmatch(r"python[\d.]*|py", name) else name
    return out


class PermissionPolicy:
    def __init__(self, workspace: Path, mode: str = "ask"):
        self.workspace = Path(workspace)
        self.mode = mode if mode in ("ask", "auto_edits") else "ask"
        self.granted: set[str] = set()

    def grant(self, key: str) -> None:
        if key:
            self.granted.add(key)

    def decide(self, spec: ToolSpec, args: dict) -> Decision:
        path = args.get("path")
        if isinstance(path, str):
            try:
                target = safe_join(self.workspace, path or ".")
            except UnsafePath as exc:
                return Decision(DENY, str(exc))
            if spec.risk == "read" and SENSITIVE_NAME.search(target.name):
                return Decision(ASK, "Archivo posiblemente sensible: su contenido se enviaría al modelo.", f"read:{target.name}", f"Leer {path}")
        if spec.risk == "read":
            return Decision(ALLOW, "Lectura dentro del espacio de trabajo.")
        if spec.risk == "destructive":
            return Decision(ASK, "Acción destructiva: necesita confirmación explícita.", "", f"{spec.name} {path or ''}".strip())
        if spec.risk == "write":
            detail = f"{spec.name} {path or ''}".strip()
            if self.mode == "auto_edits" or spec.name in self.granted:
                return Decision(ALLOW, "Edición permitida en el espacio de trabajo.", spec.name, detail)
            return Decision(ASK, "Modifica archivos del proyecto.", spec.name, detail)
        if spec.name == "run_tests":
            return self._command_decision(["python", "-m", "pytest"], safe=True, detail="Ejecutar las pruebas del proyecto")
        return self._decide_command(args)

    def _decide_command(self, args: dict) -> Decision:
        try:
            argv = parse_command(args.get("command"))
        except ToolError as exc:
            return Decision(DENY, str(exc))
        norm = _norm(argv)
        head = norm[0]
        detail = "Ejecutar: " + " ".join(argv)
        if head in NEVER or head.startswith("mkfs"):
            return Decision(DENY, f"«{head}» está bloqueado. Para borrar archivos usa delete_file.")
        if head in SHELLS:
            return Decision(DENY, "No se permiten shells (se saltarían las validaciones). Ejecuta el programa directamente.")
        for a in argv[1:]:
            if a.startswith("-") and "=" not in a:
                continue
            candidate = a.split("=", 1)[1] if a.startswith("-") and "=" in a else a
            if candidate.startswith(("/", "~")) or ".." in re.split(r"[\\/]", candidate) or re.match(r"^[A-Za-z]:[\\/]", candidate):
                if not self._inside(candidate):
                    return Decision(DENY, f"El argumento «{a}» apunta fuera del espacio de trabajo.")
        if head in INSTALLERS:
            return Decision(ASK, "Instala software: requiere autorización explícita cada vez.", "", detail)
        safe = any(norm[:len(p)] == p for p in SAFE_PREFIXES)
        return self._command_decision(norm, safe, detail)

    def _command_decision(self, norm: list[str], safe: bool, detail: str) -> Decision:
        key = "cmd:" + " ".join(norm[:3])
        if safe and (self.mode == "auto_edits" or key in self.granted):
            return Decision(ALLOW, "Comando de comprobación permitido.", key, detail)
        return Decision(ASK, "Ejecuta un programa en tu equipo." if not safe else "Comando de comprobación.", key if safe else "", detail)

    def _inside(self, candidate: str) -> bool:
        try:
            p = Path(candidate).expanduser()
            if not p.is_absolute():
                p = self.workspace / p
            p.resolve().relative_to(self.workspace.resolve())
            return True
        except (ValueError, OSError):
            return False
