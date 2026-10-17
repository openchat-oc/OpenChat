"""Contrato común de los proveedores de IA."""
from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Iterator


class ProviderError(Exception):
    """Error de proveedor con una categoría estable para que la interfaz actúe en consecuencia."""
    # kind: auth | credits | rate | network | timeout | model | server | unavailable | empty | other
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


class Cancelled(Exception):
    pass


class CancelToken:
    """Permite cancelar una generación aunque el hilo esté bloqueado leyendo de la red."""
    def __init__(self) -> None:
        self._ev = threading.Event()
        self._cbs: list[Callable[[], None]] = []
        self._lock = threading.Lock()

    def is_set(self) -> bool:
        return self._ev.is_set()

    def cancel(self) -> None:
        with self._lock:
            self._ev.set()
            cbs, self._cbs = self._cbs, []
        for cb in cbs:
            try:
                cb()
            except Exception:
                pass

    def on_cancel(self, cb: Callable[[], None]) -> None:
        with self._lock:
            if not self._ev.is_set():
                self._cbs.append(cb)
                return
        cb()

    def raise_if_cancelled(self) -> None:
        if self._ev.is_set():
            raise Cancelled()


@dataclass
class CheckResult:
    ok: bool
    message: str


class Provider(ABC):
    name = "base"
    label = "Proveedor"
    is_local = False
    last_finish_reason: str | None = None

    @abstractmethod
    def check(self) -> CheckResult: ...

    @abstractmethod
    def list_models(self) -> list[str]: ...

    @abstractmethod
    def stream_chat(self, messages: list[dict], model: str, cancel: CancelToken,
                    temperature: float = 0.6) -> Iterator[str]: ...
