"""Trabajo en segundo plano: la interfaz nunca espera a la red, a Ollama ni a un comando."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Signal

from ..agent import AgentRunner, PermissionPolicy, ToolContext
from ..config import redact
from ..providers import CancelToken, Cancelled, Provider, ProviderError


class _Bridge(QObject):
    ok = Signal(object)
    err = Signal(object)


def run_async(fn: Callable[[], object], on_ok: Callable[[object], None], on_err: Callable[[Exception], None] | None = None,
              parent: QObject | None = None) -> None:
    """Ejecuta ``fn`` en un hilo y entrega el resultado en el hilo de la interfaz."""
    bridge = _Bridge(parent)
    bridge.ok.connect(lambda v: (on_ok(v), bridge.deleteLater()))
    bridge.err.connect(lambda e: ((on_err(e) if on_err else None), bridge.deleteLater()))

    def target() -> None:
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001
            bridge.err.emit(exc)
        else:
            bridge.ok.emit(result)

    threading.Thread(target=target, daemon=True).start()


class PermissionHolder:
    def __init__(self) -> None:
        self.event = threading.Event()
        self.answer = "deny"


@dataclass
class GenRequest:
    messages: list[dict]                      # contexto ya recortado (con mensaje de sistema)
    provider: Provider
    model: str
    label: str
    temperature: float = 0.6
    fallback: tuple[Provider, str, str] | None = None     # (proveedor, modelo, etiqueta) si está activado
    agent: dict | None = None                 # {"workspace": Path, "mode": str, "history": list}


class GenerationWorker(QObject):
    chunk = Signal(str)
    status = Signal(str)
    notice = Signal(str)
    step_start = Signal()
    step_end = Signal(str)
    tool_call = Signal(object)
    tool_result = Signal(object)
    permission = Signal(str, object, object, object)   # nombre, args, decision, holder
    finished = Signal(str, str, str)                   # texto final, etiqueta, motivo («», «truncated»)
    failed = Signal(str, str, str)                     # tipo, mensaje, texto parcial
    cancelled = Signal(str)                            # texto parcial

    FALLBACK_KINDS = {"network", "timeout", "rate", "credits", "server", "unavailable"}

    def __init__(self, req: GenRequest):
        super().__init__()
        self.req = req
        self.token = CancelToken()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def cancel(self) -> None:
        self.token.cancel()

    # --------------------------------------------------------------
    def _run(self) -> None:
        try:
            if self.req.agent:
                self._run_agent()
                return
            self.status.emit("Preparando la solicitud")
            text, label = self._stream(self.req.provider, self.req.model, self.req.label, self.req.messages)
            self.finished.emit(text, label, "truncated" if self.req.provider.last_finish_reason == "length" else "")
        except Cancelled:
            self.cancelled.emit(self._partial)
        except ProviderError as exc:
            self.failed.emit(exc.kind, redact(exc.message), self._partial)
        except Exception as exc:  # noqa: BLE001 - nada debe cerrar la aplicación
            self.failed.emit("other", redact(f"Error inesperado: {exc}"), self._partial)

    _partial = ""

    def _stream(self, provider: Provider, model: str, label: str, messages: list[dict]) -> tuple[str, str]:
        self._partial = ""
        self.status.emit("Esperando la respuesta del modelo")
        try:
            first = True
            for piece in provider.stream_chat(messages, model, self.token, self.req.temperature):
                if first:
                    self.status.emit("Recibiendo texto")
                    first = False
                self._partial += piece
                self.chunk.emit(piece)
            return self._partial, label
        except ProviderError as exc:
            fb = self.req.fallback
            if fb and fb[0] is not provider and not self._partial and exc.kind in self.FALLBACK_KINDS and not self.token.is_set():
                self.notice.emit(f"{provider.label} falló ({redact(exc.message)}) → usando {fb[2]} "
                                 "porque tienes activado el respaldo automático en Ajustes.")
                return self._stream(fb[0], fb[1], fb[2], messages)
            raise

    def _run_agent(self) -> None:
        cfg = self.req.agent or {}
        ws = Path(cfg["workspace"])
        ctx = ToolContext(ws, self.token)
        policy = PermissionPolicy(ws, cfg.get("mode", "ask"))

        def emit(kind: str, payload: object) -> None:
            if kind == "status":
                self.status.emit(str(payload))
            elif kind == "delta":
                self.chunk.emit(str(payload))
            elif kind == "step_start":
                self.step_start.emit()
            elif kind == "step_end":
                self.step_end.emit(str(payload))
            elif kind == "tool_call":
                self.tool_call.emit(payload)
            elif kind == "tool_result":
                self.tool_result.emit(payload)

        def ask(name: str, args: dict, decision) -> str:
            holder = PermissionHolder()
            self.permission.emit(name, args, decision, holder)
            while not holder.event.wait(0.1):
                if self.token.is_set():
                    return "deny"
            return holder.answer

        runner = AgentRunner(self.req.provider, self.req.model, ctx, policy, emit, ask, temperature=0.3)
        result = runner.run(cfg["history"])
        if result.stopped == "cancelled":
            self.cancelled.emit("")
        else:
            self.finished.emit(result.final_text, self.req.label, result.stopped)
