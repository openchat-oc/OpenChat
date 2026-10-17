"""Servidor HTTP local que imita OpenRouter (SSE) y Ollama (JSON por líneas) para pruebas reales de red."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def make_server(routes):
    """routes: {(method, path): callable(handler, body)->None}"""
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _go(self, method):
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"null") if n else None
            fn = routes.get((method, self.path.split("?")[0]))
            if not fn:
                self.send_response(404); self.end_headers(); return
            fn(self, body)
        def do_GET(self): self._go("GET")
        def do_POST(self): self._go("POST")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def send_json(h, status, obj):
    data = json.dumps(obj).encode()
    h.send_response(status); h.send_header("Content-Type", "application/json")
    h.send_header("Content-Length", str(len(data))); h.end_headers(); h.wfile.write(data)


def sse(h, chunks, finish="stop", delay=0.0, comment=True):
    import time
    h.send_response(200); h.send_header("Content-Type", "text/event-stream"); h.end_headers()
    if comment:
        h.wfile.write(b": OPENROUTER PROCESSING\n\n"); h.wfile.flush()
    for c in chunks:
        h.wfile.write(b"data: " + json.dumps({"choices": [{"delta": {"content": c}}]}).encode() + b"\n\n"); h.wfile.flush()
        time.sleep(delay)
    h.wfile.write(b"data: " + json.dumps({"choices": [{"delta": {}, "finish_reason": finish}]}).encode() + b"\n\n")
    h.wfile.write(b"data: [DONE]\n\n"); h.wfile.flush()
