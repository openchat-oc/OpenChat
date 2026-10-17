"""Cliente de Ollama (local, en 127.0.0.1). No envía nada a Internet."""
from __future__ import annotations

import json
from typing import Callable, Iterator

import requests

from .base import CancelToken, CheckResult, Cancelled, Provider, ProviderError

BASE = "http://127.0.0.1:11434"


class OllamaProvider(Provider):
    name = "ollama"
    label = "Ollama"
    is_local = True

    def __init__(self, base: str = BASE, session: requests.Session | None = None):
        self.base = base.rstrip("/")
        self.http = session or requests.Session()

    def _down(self) -> ProviderError:
        return ProviderError("unavailable",
                             "Ollama no responde en 127.0.0.1:11434. Comprueba que está instalado y en ejecución (ollama serve).")

    def installed_models(self) -> list[dict]:
        try:
            r = self.http.get(self.base + "/api/tags", timeout=(2, 6))
            r.raise_for_status()
            return list(r.json().get("models", []))
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise self._down() from exc
        except (requests.RequestException, ValueError) as exc:
            raise ProviderError("other", f"Respuesta inesperada de Ollama: {exc}") from exc

    def list_models(self) -> list[str]:
        return [m["name"] for m in self.installed_models() if m.get("name")]

    def check(self, model: str | None = None) -> CheckResult:
        try:
            names = self.list_models()
        except ProviderError as exc:
            return CheckResult(False, exc.message)
        if not names:
            return CheckResult(False, "Ollama funciona, pero no hay ningún modelo descargado.")
        if model and model not in names:
            return CheckResult(False, f"Ollama funciona, pero el modelo «{model}» no está descargado.")
        return CheckResult(True, "Ollama funciona y hay modelos disponibles.")

    def stream_chat(self, messages, model, cancel: CancelToken, temperature: float = 0.6) -> Iterator[str]:
        self.last_finish_reason = None
        payload = {"model": model, "messages": messages, "stream": True, "options": {"temperature": temperature}}
        try:
            resp = self.http.post(self.base + "/api/chat", json=payload, stream=True, timeout=(2, 120))
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise self._down() from exc
        except requests.RequestException as exc:
            raise ProviderError("other", str(exc)) from exc
        cancel.on_cancel(resp.close)
        got_text = False
        try:
            if resp.status_code == 404:
                raise ProviderError("model", f"El modelo «{model}» no está descargado en Ollama.")
            if resp.status_code != 200:
                raise ProviderError("server", f"Ollama devolvió el error {resp.status_code}: {resp.text[:200]}")
            for raw in resp.iter_lines():
                cancel.raise_if_cancelled()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw.decode("utf-8", "replace"))
                except ValueError:
                    continue
                if obj.get("error"):
                    raise ProviderError("server", f"Ollama: {obj['error']}")
                piece = (obj.get("message") or {}).get("content")
                if piece:
                    got_text = True
                    yield piece
                if obj.get("done"):
                    self.last_finish_reason = obj.get("done_reason") or "stop"
                    break
        except requests.RequestException as exc:
            if cancel.is_set():
                raise Cancelled() from exc
            raise self._down() from exc
        except (ValueError, OSError) as exc:
            if cancel.is_set():
                raise Cancelled() from exc
            raise ProviderError("network", "Se interrumpió la conexión con Ollama.") from exc
        finally:
            resp.close()
        if cancel.is_set():
            raise Cancelled()
        if not got_text:
            raise ProviderError("empty", "Ollama no devolvió texto.")

    def pull(self, model: str, cancel: CancelToken, on_progress: Callable[[str, int, int], None]) -> None:
        """Descarga un modelo informando (estado, completado, total). Cancelable."""
        try:
            resp = self.http.post(self.base + "/api/pull", json={"model": model, "stream": True}, stream=True, timeout=(2, 120))
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise self._down() from exc
        cancel.on_cancel(resp.close)
        try:
            if resp.status_code != 200:
                raise ProviderError("model", f"No se pudo descargar «{model}» (error {resp.status_code}).")
            ok = False
            for raw in resp.iter_lines():
                cancel.raise_if_cancelled()
                if not raw:
                    continue
                obj = json.loads(raw.decode("utf-8", "replace"))
                if obj.get("error"):
                    raise ProviderError("model", f"Ollama: {obj['error']}")
                status = obj.get("status", "")
                on_progress(status, int(obj.get("completed") or 0), int(obj.get("total") or 0))
                if status == "success":
                    ok = True
            if not ok:
                raise ProviderError("model", "La descarga terminó sin confirmar que el modelo esté listo.")
        except (requests.RequestException, OSError, ValueError) as exc:
            if cancel.is_set():
                raise Cancelled() from exc
            raise ProviderError("network", f"Se interrumpió la descarga: {exc}") from exc
        finally:
            resp.close()
