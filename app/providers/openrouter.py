"""Cliente de OpenRouter (nube). Usa la API compatible con OpenAI con streaming SSE."""
from __future__ import annotations

import json
from typing import Iterator

import requests

from .. import REPO_URL
from ..config import redact
from .base import CancelToken, CheckResult, Cancelled, Provider, ProviderError

BASE = "https://openrouter.ai/api/v1"


def _error_text(resp: requests.Response) -> str:
    try:
        data = resp.json()
        err = data.get("error", data)
        if isinstance(err, dict):
            return str(err.get("message") or err)[:300]
        return str(err)[:300]
    except Exception:
        return (resp.text or "")[:300]


def map_http_error(status: int, detail: str) -> ProviderError:
    detail = redact(detail)
    if status in (401, 403):
        return ProviderError("auth", "OpenRouter rechazó la clave (no es válida o no tiene permiso).")
    if status == 402:
        return ProviderError("credits", "Créditos insuficientes en OpenRouter para este modelo.")
    if status == 429:
        return ProviderError("rate", "Se alcanzó el límite de uso de OpenRouter. Espera un momento o cambia de modelo.")
    if status in (400, 404):
        return ProviderError("model", f"El modelo no está disponible o la solicitud no es válida. {detail}".strip())
    if status == 408:
        return ProviderError("timeout", "OpenRouter tardó demasiado en responder.")
    if status >= 500:
        return ProviderError("server", f"OpenRouter tiene un problema temporal ({status}). {detail}".strip())
    return ProviderError("other", f"Error {status} de OpenRouter. {detail}".strip())


class OpenRouterProvider(Provider):
    name = "openrouter"
    label = "OpenRouter"
    is_local = False

    def __init__(self, api_key: str, base: str = BASE, session: requests.Session | None = None):
        self.api_key = api_key.strip()
        self.base = base.rstrip("/")
        self.http = session or requests.Session()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json",
                "HTTP-Referer": REPO_URL, "X-Title": "OpenChat"}

    def _wrap(self, exc: Exception) -> ProviderError:
        if isinstance(exc, requests.Timeout):
            return ProviderError("timeout", "OpenRouter no respondió a tiempo.")
        if isinstance(exc, requests.ConnectionError):
            return ProviderError("network", "No hay conexión con OpenRouter. Revisa tu Internet.")
        return ProviderError("other", redact(exc))

    def check(self) -> CheckResult:
        if not self.api_key:
            return CheckResult(False, "Falta la clave de OpenRouter.")
        try:
            r = self.http.get(self.base + "/key", headers=self._headers(), timeout=(5, 12))
        except requests.RequestException as exc:
            return CheckResult(False, self._wrap(exc).message)
        if r.status_code == 200:
            return CheckResult(True, "Conexión con OpenRouter correcta; la clave es válida.")
        return CheckResult(False, map_http_error(r.status_code, _error_text(r)).message)

    def list_models(self) -> list[str]:
        try:
            r = self.http.get(self.base + "/models", headers=self._headers(), timeout=(5, 20))
            r.raise_for_status()
            return sorted(m["id"] for m in r.json().get("data", []) if m.get("id"))
        except requests.RequestException as exc:
            raise self._wrap(exc) from exc
        except (ValueError, KeyError) as exc:
            raise ProviderError("other", "Respuesta inesperada al listar modelos.") from exc

    def stream_chat(self, messages, model, cancel: CancelToken, temperature: float = 0.6) -> Iterator[str]:
        self.last_finish_reason = None
        payload = {"model": model, "messages": messages, "temperature": temperature, "stream": True}
        try:
            resp = self.http.post(self.base + "/chat/completions", headers=self._headers(),
                                  json=payload, stream=True, timeout=(5, 45))
        except requests.RequestException as exc:
            raise self._wrap(exc) from exc
        cancel.on_cancel(resp.close)
        got_text = False
        try:
            if resp.status_code != 200:
                raise map_http_error(resp.status_code, _error_text(resp))
            for raw in resp.iter_lines():
                cancel.raise_if_cancelled()
                if not raw:
                    continue
                line = raw.decode("utf-8", "replace").strip()
                if line.startswith(":"):          # comentarios keep-alive de OpenRouter
                    continue
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except ValueError:
                    continue
                if obj.get("error"):
                    err = obj["error"]
                    msg = err.get("message") if isinstance(err, dict) else str(err)
                    raise ProviderError("server", redact(f"El modelo devolvió un error: {msg}"))
                for choice in obj.get("choices", []):
                    delta = choice.get("delta") or choice.get("message") or {}
                    piece = delta.get("content")
                    if isinstance(piece, list):
                        piece = "".join(p.get("text", "") for p in piece if isinstance(p, dict))
                    if piece:
                        got_text = True
                        yield piece
                    if choice.get("finish_reason"):
                        self.last_finish_reason = choice["finish_reason"]
        except requests.RequestException as exc:
            if cancel.is_set():
                raise Cancelled() from exc
            raise self._wrap(exc) from exc
        except (ValueError, OSError) as exc:      # resp.close() desde otro hilo
            if cancel.is_set():
                raise Cancelled() from exc
            raise ProviderError("network", "Se interrumpió la conexión con OpenRouter.") from exc
        finally:
            resp.close()
        if cancel.is_set():
            raise Cancelled()
        if not got_text:
            raise ProviderError("empty", "El modelo no devolvió texto.")
