"""Asistente de configuración contra servidores falsos (OpenRouter y Ollama) con Qt offscreen."""
import json
import time

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication

import app.ui.wizard as wz
from app import config
from app.providers import OllamaProvider, OpenRouterProvider
from app.ui.theme import QSS
from tests.fakeserver import make_server, send_json
from tests.test_providers import KEY, ollama_routes
from tests.test_ui import close_windows, pump, qapp  # noqa: F401  (fixtures compartidas)


@pytest.fixture
def servers(monkeypatch):
    def key(h, body): send_json(h, 200 if h.headers["Authorization"] == "Bearer " + KEY else 401, {"data": {}})
    def models(h, body): send_json(h, 200, {"data": [{"id": "a/b:free"}, {"id": "c/d"}]})
    or_srv, or_url = make_server({("GET", "/key"): key, ("GET", "/models"): models})
    ol_srv, ol_url = make_server(ollama_routes(models=("qwen2.5:1.5b",)))
    monkeypatch.setattr(wz, "OpenRouterProvider", lambda k: OpenRouterProvider(k, base=or_url))
    monkeypatch.setattr(wz, "OllamaProvider", lambda: OllamaProvider(base=ol_url))
    yield
    or_srv.shutdown(); ol_srv.shutdown()


def test_cloud_flow_requires_real_check_then_saves_everything(qapp, servers):
    s = config.Settings(); d = wz.SetupWizard(s); d.show()
    d._next(); d.r_cloud.setChecked(True); d._next()                          # bienvenida → motor → nube
    assert d.stack.currentIndex() == wz.CLOUD and not d.next_btn.isEnabled()
    d.key_edit.setText("sk-or-v1-claveinvalidaclaveinvalida"); d._check_cloud()
    assert pump(qapp, lambda: d.check_btn.isEnabled()) and not d.cloud_ok and not d.next_btn.isEnabled()
    assert "rechaz" in d.cloud_status.text()
    d.show_btn.setChecked(True); assert d.key_edit.echoMode().name == "Normal"
    d.key_edit.setText(KEY); d._check_cloud()
    assert pump(qapp, lambda: d.cloud_ok) and d.next_btn.isEnabled()
    d._load_models(); assert pump(qapp, lambda: d.model_combo.count() == 2)
    d.model_combo.setCurrentText("c/d"); d.fb_check.setChecked(True)
    d._next(); assert d.stack.currentIndex() == wz.DONE and "c/d" in d.summary.text()
    d._next()                                                                   # Terminar
    s2 = config.Settings()
    assert s2["setup_done"] and s2["mode"] == "cloud" and s2["cloud_model"] == "c/d" and s2["fallback_to_local"]
    assert config.get_api_key() == KEY


def test_cancelling_wizard_saves_nothing(qapp, servers):
    s = config.Settings(); d = wz.SetupWizard(s); d.show()
    d._next(); d.r_cloud.setChecked(True); d._next(); d.key_edit.setText(KEY); d._check_cloud()
    assert pump(qapp, lambda: d.cloud_ok)
    d._cancel()
    assert not config.Settings().loaded_from_disk and config.get_api_key() == ""


def test_local_flow_needs_an_installed_model(qapp, servers):
    s = config.Settings(); d = wz.SetupWizard(s); d.show()
    d._next(); d.r_local.setChecked(True); d._next()
    assert d.stack.currentIndex() == wz.LOCAL
    assert pump(qapp, lambda: d.local_combo.count() == 1) and d.next_btn.isEnabled()
    assert "funciona" in d.ollama_status.text()
    d._next(); d._next()
    s2 = config.Settings()
    assert s2["mode"] == "local" and s2["local_model"] == "qwen2.5:1.5b" and s2["setup_done"]
    assert config.get_api_key() == ""                                           # local: no se pide ni guarda clave


def test_local_page_without_ollama_explains_and_blocks(qapp, monkeypatch):
    monkeypatch.setattr(wz, "OllamaProvider", lambda: OllamaProvider(base="http://127.0.0.1:9"))
    d = wz.SetupWizard(config.Settings()); d.show()
    d._next(); d.r_local.setChecked(True); d._next()
    assert pump(qapp, lambda: "no responde" in d.ollama_status.text())
    assert not d.next_btn.isEnabled() and "ollama" in d.ollama_help.text().lower()


def test_model_download_reports_progress_and_updates_list(qapp, monkeypatch):
    state = {"pulled": False}
    routes = ollama_routes(models=())
    def tags(h, body): send_json(h, 200, {"models": [{"name": "qwen2.5:1.5b"}] if state["pulled"] else []})
    orig_pull = routes[("POST", "/api/pull")]
    def pull(h, body): orig_pull(h, body); state["pulled"] = True
    routes[("GET", "/api/tags")] = tags; routes[("POST", "/api/pull")] = pull
    srv, url = make_server(routes)
    monkeypatch.setattr(wz, "OllamaProvider", lambda: OllamaProvider(base=url))
    d = wz.SetupWizard(config.Settings()); d.show(); d._next(); d.r_local.setChecked(True); d._next()
    assert pump(qapp, lambda: "ningún modelo" in d.ollama_status.text()) and not d.next_btn.isEnabled()
    d._start_pull()
    assert pump(qapp, lambda: "descargado" in d.pull_label.text()) and pump(qapp, lambda: d.local_combo.count() == 1)
    assert d.next_btn.isEnabled()
    srv.shutdown()
