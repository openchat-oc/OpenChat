import json
import threading
import time

import pytest

from app.providers import CancelToken, Cancelled, OllamaProvider, OpenRouterProvider, ProviderError
from tests.fakeserver import make_server, send_json, sse

KEY = "sk-or-v1-TESTKEYTESTKEYTESTKEY1234"


def collect(gen):
    return "".join(gen)


def test_openrouter_streams_and_sends_selected_model():
    seen = {}
    def chat(h, body):
        seen.update(body=body, auth=h.headers["Authorization"])
        sse(h, ["Hola", " mun", "do\nlínea 2"])
    srv, url = make_server({("POST", "/chat/completions"): chat})
    p = OpenRouterProvider(KEY, base=url)
    assert collect(p.stream_chat([{"role": "user", "content": "hi"}], "modelo/elegido:free", CancelToken())) == "Hola mundo\nlínea 2"
    assert seen["body"]["model"] == "modelo/elegido:free" and seen["body"]["stream"] is True
    assert seen["auth"] == "Bearer " + KEY
    assert p.last_finish_reason == "stop"
    srv.shutdown()


@pytest.mark.parametrize("status,kind", [(401, "auth"), (402, "credits"), (429, "rate"), (404, "model"), (503, "server")])
def test_openrouter_http_errors_are_classified_and_never_leak_key(status, kind):
    def chat(h, body): send_json(h, status, {"error": {"message": f"fallo con {KEY}"}})
    srv, url = make_server({("POST", "/chat/completions"): chat})
    p = OpenRouterProvider(KEY, base=url)
    with pytest.raises(ProviderError) as ei:
        collect(p.stream_chat([], "m", CancelToken()))
    assert ei.value.kind == kind and "TESTKEY" not in ei.value.message
    srv.shutdown()


def test_openrouter_check_valid_and_invalid_key():
    def key(h, body):
        send_json(h, 200 if h.headers["Authorization"] == "Bearer " + KEY else 401, {"data": {}})
    srv, url = make_server({("GET", "/key"): key})
    assert OpenRouterProvider(KEY, base=url).check().ok
    bad = OpenRouterProvider("sk-or-v1-otra-clave-distinta-0000", base=url).check()
    assert not bad.ok and "rechaz" in bad.message
    assert not OpenRouterProvider("", base=url).check().ok
    srv.shutdown()


def test_openrouter_network_error_is_not_an_auth_error():
    r = OpenRouterProvider(KEY, base="http://127.0.0.1:9").check()      # puerto cerrado
    assert not r.ok and "conexión" in r.message.lower()


def test_openrouter_inline_error_and_empty_response():
    def chat(h, body):
        h.send_response(200); h.end_headers()
        h.wfile.write(b'data: {"error": {"message": "proveedor caido"}}\n\n')
    srv, url = make_server({("POST", "/chat/completions"): chat})
    with pytest.raises(ProviderError) as ei:
        collect(OpenRouterProvider(KEY, base=url).stream_chat([], "m", CancelToken()))
    assert "caido" in ei.value.message
    srv.shutdown()
    def empty(h, body): sse(h, [])
    srv, url = make_server({("POST", "/chat/completions"): empty})
    with pytest.raises(ProviderError) as ei:
        collect(OpenRouterProvider(KEY, base=url).stream_chat([], "m", CancelToken()))
    assert ei.value.kind == "empty"
    srv.shutdown()


def test_openrouter_cancel_stops_a_slow_stream_quickly():
    def chat(h, body):
        try: sse(h, ["x"] * 200, delay=0.05)
        except (BrokenPipeError, ConnectionResetError): pass
    srv, url = make_server({("POST", "/chat/completions"): chat})
    p, tok, got = OpenRouterProvider(KEY, base=url), CancelToken(), []
    def run():
        try:
            for piece in p.stream_chat([], "m", tok): got.append(piece)
        except Cancelled: got.append("CANCELLED")
    t = threading.Thread(target=run); t.start()
    time.sleep(0.4); t0 = time.time(); tok.cancel(); t.join(3)
    assert not t.is_alive() and got[-1] == "CANCELLED" and time.time() - t0 < 1.5
    assert len(got) < 100
    srv.shutdown()


def ollama_routes(models=("qwen2.5:1.5b",), reply=("Ho", "la")):
    def tags(h, body): send_json(h, 200, {"models": [{"name": m, "size": 1} for m in models]})
    def chat(h, body):
        if body["model"] not in models:
            send_json(h, 404, {"error": "model not found"}); return
        h.send_response(200); h.end_headers()
        for c in reply:
            h.wfile.write(json.dumps({"message": {"content": c}, "done": False}).encode() + b"\n")
        h.wfile.write(json.dumps({"message": {"content": ""}, "done": True, "done_reason": "stop"}).encode() + b"\n")
    def pull(h, body):
        h.send_response(200); h.end_headers()
        for obj in ({"status": "pulling", "total": 100, "completed": 50}, {"status": "pulling", "total": 100, "completed": 100}, {"status": "success"}):
            h.wfile.write(json.dumps(obj).encode() + b"\n"); h.wfile.flush()
    return {("GET", "/api/tags"): tags, ("POST", "/api/chat"): chat, ("POST", "/api/pull"): pull}


def test_ollama_models_chat_and_missing_model():
    srv, url = make_server(ollama_routes())
    p = OllamaProvider(base=url)
    assert p.list_models() == ["qwen2.5:1.5b"] and p.check("qwen2.5:1.5b").ok
    assert collect(p.stream_chat([], "qwen2.5:1.5b", CancelToken())) == "Hola"
    with pytest.raises(ProviderError) as ei:
        collect(p.stream_chat([], "no-existe", CancelToken()))
    assert ei.value.kind == "model"
    assert not p.check("otro").ok
    srv.shutdown()


def test_ollama_service_down_and_no_models():
    p = OllamaProvider(base="http://127.0.0.1:9")
    assert not p.check().ok and "no responde" in p.check().message
    with pytest.raises(ProviderError) as ei:
        p.list_models()
    assert ei.value.kind == "unavailable"
    srv, url = make_server(ollama_routes(models=()))
    assert "ningún modelo" in OllamaProvider(base=url).check().message
    srv.shutdown()


def test_ollama_pull_reports_progress_and_requires_success():
    srv, url = make_server(ollama_routes())
    events = []
    OllamaProvider(base=url).pull("qwen2.5:1.5b", CancelToken(), lambda s, c, t: events.append((s, c, t)))
    assert events[0] == ("pulling", 50, 100) and events[-1][0] == "success"
    srv.shutdown()
